#!/usr/bin/env python

# Copyright (C) 2018 by eHealth Africa : http://www.eHealthAfrica.org
#
# See the NOTICE file distributed with this work for additional information
# regarding copyright ownership.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

import enum
from datetime import datetime
import json
from jsonschema import validate
import redis
import requests
from requests.auth import HTTPBasicAuth
import signal
import threading
from time import sleep

from aet.consumer import KafkaConsumer

from . import settings
from .api import APIServer
from .jsonpath import CachedParser
from .logger import LOG

EXCLUDED_TOPICS = ['__confluent.support.metrics']


class RESTConsumer(object):

    def __init__(self, CSET, KSET):
        self.serve_api(CSET)
        self.redis_db = CSET['REDIS_DB']
        self.redis = redis.Redis(
            host=CSET['REDIS_HOST'],
            port=CSET['REDIS_PORT'],
            db=self.redis_db,
            encoding="utf-8",
            decode_responses=True
        )
        self.consumer_settings = CSET
        self.kafka_settings = KSET
        self.recent_changes = []  # To keep track of changes in config
        self.children = {}
        self.schema = self.load_schema()
        self.subscribe_to_jobs()
        self.load_existing_jobs()
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)

    def serve_api(self, settings):
        self.api = APIServer(self, settings)
        self.api.serve()

    def subscribe_to_jobs(self):
        key_space = f'__keyspace@{self.redis_db}__:_job:*'
        LOG.debug(f'Subscribing to {key_space}')
        self.pubsub = self.redis.pubsub()
        self.pubsub.psubscribe(**{
            f'{key_space}': self.handle_job_change
        }
        )
        self.subscriber = self.pubsub.run_in_thread(sleep_time=0.1)

    def handle_job_change(self, msg):
        _id = msg['channel'].split('job:')[1]
        op = msg['data']
        self.recent_changes.append(
            tuple([_id, op, str(datetime.now().isoformat())
                   ]))
        self.recent_changes = self.recent_changes[-10::]
        if op == 'del':
            return self.stop_child(_id)
        elif op == 'set':
            return self.upstart_child(_id)
        else:
            raise ValueError('''Unexpected operation {op} on channel {msg['channel']}''')

    def load_existing_jobs(self):
        # Get existing jobs from Redis and start up.
        for _id in self.list_jobs():
            self.upstart_child(_id)

    def upstart_child(self, _id):
        LOG.debug(f'handling update for job:{_id}')
        if _id in self.children.keys():
            LOG.debug(f'Child {_id} exists, updating')
            try:
                config = self.get_job(_id)
            except ValueError:
                LOG.error(f'Could not update deleted job {_id}')
                return
            fn = self.children[_id].update_config
            threading.Thread(target=fn, args=(config,)).start()
        else:
            LOG.debug(f'Starting child {_id}')
            try:
                config = self.get_job(_id)
            except ValueError:
                LOG.error(f'Could not start job {_id}, no matching config found in Redis')
                return
            self.children[_id] = RESTWorker(_id, config, self.kafka_settings)

    def stop_child(self, _id):
        LOG.debug(f'handling removal for job:{_id}')
        try:
            thread = self.children[_id].stop()
            thread.join()
            self.children[_id].running = False
            del self.children[_id]
            return True
        except KeyError:
            LOG.error(f'Could not remove job {_id}, no matching job found')

    def stop_all_children(self):
        children = list(self.children.keys())  # we modify the dict, so we need a copy
        for _id in children:
            try:
                LOG.info(f'Stopping child {_id}')
                self.stop_child(_id)
            except KeyError:
                LOG.info(f'Could not find child {_id} to stop')

    def stop(self, *args, **kwargs):
        LOG.info('Shutting down')
        try:
            self.subscriber.stop()
        except AttributeError:
            pass
        self.stop_all_children()
        self.api.stop()
        LOG.info('Shutdown Complete')

    # Generic Redis Task Functions

    def _add_task(self, task, type):
        key = f'''_{type}:{task['id']}'''
        task['modified'] = datetime.now().isoformat()
        return self.redis.set(key, json.dumps(task))

    def _task_exists(self, _id, type):
        task_id = f'_{type}:{_id}'
        if self.redis.exists(task_id):
            return True
        return False

    def _remove_task(self, _id, type):
        task_id = f'_{type}:{_id}'
        res = self.redis.delete(task_id)
        if not res:
            return False
        return True

    def _get_task(self, _id, type):
        task_id = f'_{type}:{_id}'
        task = self.redis.get(task_id)
        if not task:
            raise ValueError(f'No task with id {task_id}')
        return task

    def _list_tasks(self, type=None):
        # jobs as a generator
        if type:
            key_identifier = f'_{type}:*'
        else:
            key_identifier = '*'
        for i in self.redis.scan_iter(key_identifier):
            yield str(i).split(key_identifier[:-1])[1]

    # Job Functions

    def load_schema(self):
        with open('./app/job_schema.json') as f:
            return json.load(f)

    def validate_job(self, job):
        validate(job, self.schema)  # Throws ValidationErrors

    def add_job(self, job):
        self.validate_job(job)
        return self._add_task(job, type='job')

    def job_exists(self, _id):
        return self._task_exists(_id, type='job')

    def remove_job(self, _id):
        return self._remove_task(_id, type='job')

    def get_job(self, _id):
        return json.loads(self._get_task(_id, type='job'))

    def list_jobs(self):
        status = {}
        for job in self._list_tasks(type='job'):
            if job in self.children:
                status[job] = str(self.children.get(job).status)
            else:
                status[job] = 'unknown'
        return status


class WorkerException(Exception):
    # A class to handle anticipated exceptions
    pass


class WorkerStatus(enum.Enum):
    STARTED = 1
    RUNNING = 2
    ERR_KAFKA = 3
    ERR_CONFIG = 4
    ERR_DELIVERY = 5


class RESTWorker(object):

    REST_CALLS = {  # Available calls mirrored in json schema
        "HEAD": requests.head,
        "GET": requests.get,
        "POST": requests.post,
        "PUT": requests.put,
        "DELETE": requests.delete,
        "OPTIONS": requests.options
    }

    WORK_LOOP_INTERVAL = 1  # Sleep time between messaging loops

    def __init__(self, _id, config, kafka_config):
        LOG.debug(f'Initalizing worker {_id}')
        self.running = False
        self.status = WorkerStatus.STARTED
        self._id = _id
        self.kafka_config = kafka_config
        self.kafka_group = f'RESTWorker:{_id}'
        self.worker = None
        self.topics = []
        self.consumer = None
        self.url = None
        try:
            self.update_config(config)
        except WorkerException as we:
            LOG.error(f'Could not initalize worker {self._id}: {we}')
            self.status = WorkerStatus.ERR_CONFIG

    def get_consumer(self, kconf, kafka_group, topics=[]):
        try:
            if not topics:
                raise WorkerException('No topics specified')
            args = kconf.copy()
            args['group_id'] = kafka_group
            consumer = KafkaConsumer(**args)
            consumer.subscribe(topics)
            return consumer
        except Exception as ke:
            self.status = WorkerStatus.ERR_KAFKA
            LOG.warning(f'Worker {self._id}: Could not connect to Kafka: {ke}')
            raise WorkerException('No Kafka Connection')

    def update_config(self, config):
        LOG.debug(f'Worker {self._id} has a new configuration.')
        if self.worker and self.worker.is_alive():
            LOG.debug(f'{self._id} pausing worker for update.')
            self.running = False
            self.worker.join()
            LOG.debug(f'{self._id} worker stopped.')
        # parse config / setup pipeline
        self.parse_config(config)
        # start worker with pipeline
        self.start_worker()

    def start_worker(self):
        self.worker = threading.Thread(target=self.work)
        self.running = True
        self.worker.start()

    def work(self):
        LOG.info(f'Worker on {self._id} started processing.')
        while self.running:
            if not self.consumer:
                try:
                    LOG.info(f'Worker {self._id}: Creating new Consumer Connection')
                    self.consumer = self.get_consumer(
                        self.kafka_config,
                        self.kafka_group,
                        self.topics
                    )
                    LOG.info(f'Worker {self._id}: Consumer Connected')
                except WorkerException:
                    LOG.debug(f'Worker {self._id}: Could not connect to Kafka.')
                    sleep(RESTWorker.WORK_LOOP_INTERVAL)
                    continue
            try:
                # poll for new messages
                new_messages = self.consumer.poll_and_deserialize(
                    timeout_ms=1000,
                    max_records=1)
                if new_messages:
                    LOG.debug(f'{self._id} new messages!')
            except Exception as err:
                # handle failures in polling
                self.status = WorkerStatus.ERR_KAFKA
                LOG.warning(f'Worker {self._id} Could not poll kafka: {err}')
                self.consumer.close()
                self.consumer = None
                continue
            if not new_messages:
                LOG.debug(f'{self._id} no messages')
            for parition_key, packages in new_messages.items():
                for package in packages:
                    schema = package.get('schema')
                    messages = package.get('messages')
                    for x, msg in enumerate(messages):
                        # handle each message
                        try:
                            res = self.handle_message(schema, msg)
                            LOG.debug(f'Worker: {self._id} handled' +
                                      f'msg with status {res.status_code}')
                        except Exception as err:
                            LOG.error(f'Worker {self._id}: message send failed with: {err}')
                            raise err

            self.status = WorkerStatus.RUNNING
            sleep(RESTWorker.WORK_LOOP_INTERVAL)
        if self.consumer:
            self.consumer.close()
        LOG.info(f'Worker on {self._id} is finished.')

    def parse_config(self, config):
        # Process to understand config and create pipeline
        try:
            self.url = config['url']
            self.topics = config['topic']
            self.data_map = config['datamap']
            self.constant = config.get('constant', {})
        except KeyError as err:
            LOG.error(f'Job {self._id} has a bad configuration. Job will not run. Missing: {err}')
            raise WorkerException('Bad configuration.')
        self.config = config

    def handle_message(self, schema, msg):
        whole_message = {'schema': schema, 'msg': msg, 'constant': self.constant}
        mapped_data = self.process_data_map(self.data_map, whole_message)
        return self.make_request(
            mapped_data,
            self.config
        )

    def process_data_map(self, data_spec, msg):
        # Pulls out elements from data (msg + schema) according to data_spec
        data_map = {}
        for key, path in data_spec.items():
            matches = CachedParser.find(path, msg)
            if not matches:
                continue
            if len(matches) > 1:
                data_map[key] = [m.value for m in matches]
            else:
                data_map[key] = matches[0].value
        return data_map

    def data_from_datamap(self, datamap, keys):
        # Grab requirements in keys from datamap
        data = {k: datamap.get(k) for k in keys if k in datamap}
        return data

    def make_request(self, mapped_data, config):
        request_type = config['type']
        url = config['url']
        try:
            full_url = url.format(**mapped_data)
        except KeyError as ker:
            LOG.error(f'Error sending message in job {self._id}: {ker}' +
                      f'{url} -> {mapped_data}')
            raise requests.URLRequired(f'bad argument in URL: {ker}')
        fn = self.get_request_function_for_type(request_type)
        auth = config.get('basic_auth')
        if auth:
            auth = HTTPBasicAuth(auth['user'], auth['password'])
        params = config.get('query_params')
        if params:
            params = self.data_from_datamap(mapped_data, params)
        json_body = config.get('json_body')
        if json_body:
            json_body = self.data_from_datamap(mapped_data, json_body)
        headers = config.get('token')
        if headers:
            headers = {'Authorization': f'access_token {headers}'}
        LOG.debug(f'json: {json_body}, url: {full_url}')
        return fn(
            full_url,
            auth=auth,
            headers=headers,
            params=params,
            json=json_body
        )

    def get_request_function_for_type(self, request_type):
        return RESTWorker.REST_CALLS[request_type]

    def stop(self):
        LOG.debug(f'Worker {self._id} is stopping')
        self.running = False
        return self.worker


def run():
    CSET = settings.get_CONSUMER_CONFIG()
    KSET = settings.get_KAFKA_CONFIG()
    consumer = RESTConsumer(CSET, KSET)  # noqa


if __name__ == "__main__":
    run()
