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

# from aet.consumer import KafkaConsumer

from datetime import datetime
import json
from jsonschema import validate
import redis
import requests

from . import settings
from .healthcheck import HealthcheckServer
from .jsonpath import CachedParser
from .logger import LOG

EXCLUDED_TOPICS = ['__confluent.support.metrics']


class RESTConsumer(object):

    def __init__(self, CSET, KSET):
        self.serve_healthcheck(CSET['EXPOSE_PORT'])
        self.redis_db = CSET['REDIS_DB']
        self.redis = redis.Redis(
            host=CSET['REDIS_HOST'],
            port=CSET['REDIS_PORT'],
            db=self.redis_db,
            encoding="utf-8",
            decode_responses=True
        )
        self.recent_changes = []  # To keep track of changes in config
        self.children = {}
        self.schema = self.load_schema()
        self.subscribe_to_jobs()
        self.load_existing_jobs()

    def serve_healthcheck(self, port):
        self.healthcheck = HealthcheckServer(port)
        self.healthcheck.start()

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
            LOG.debug(f'Child {id} exists, updating')
        else:
            LOG.debug(f'Starting child {_id}')
            try:
                config = self.get_job(_id)
            except ValueError:
                LOG.error(f'Could not start job {_id}, no matching config found in Redis')
                return
            self.children[_id] = RESTWorker(_id, config)

    def stop_child(self, _id):
        LOG.debug(f'handling removal for job:{_id}')
        try:
            self.children[_id].stop()
            del self.children[_id]
        except KeyError:
            LOG.error(f'Could not remove job {_id}, no matching job found')

    def stop(self):
        LOG.info('Shutting down')
        try:
            self.subscriber.stop()
        except AttributeError:
            pass
        self.healthcheck.stop()
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
            raise ValueError(f'No job with id {task_id}')
        return task

    def _list_tasks(self, type):
        # jobs as a generator
        key_identifier = f'_{type}:*'
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
        return self._list_tasks(type='job')


class RESTWorker(object):

    REST_CALLS = {
                "HEAD": requests.head,
                "GET": requests.get,
                "POST": requests.post,
                "PUT": requests.put,
                "DELETE": requests,delete,
                "OPTIONS": requests.options
            }

    def __init__(self, _id, config):
        self._id = _id
        self.worker = None
        self.topics = []
        self.consumer = None
        self.url = None
        self.update_config(config)

    def update_config(self, config):
        LOG.debug(f'Worker {self._id} has a new configuration.')
        if self.worker:
            pass  # stop worker and wait for it to pause
        self.parse_config(config)
        # parse config / setup pipeline
        # start worker with pipeline

    def parse_config(self, config):
        # Process to understand config and create pipeline
        self.config = config
        return

    def handle_message(self, schema, msg):
        whole_message = {'schema': schema, 'msg': msg}
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
        request_type = config['request_type']
        url = config['url']
        full_url = url.format(mapped_data)
        fn = self.get_request_function_for_type(request_type)
        params = config.get('query_params')
        if params:
            params = self.data_from_datamap(mapped_data, params)
        json_body = config.get('json_body')
        if json_body:
            json_body = self.data_from_datamap(mapped_data, json_body)
        return fn(
            full_url,
            params=params,
            json=json_body
        )


    def get_request_function_for_type(self, request_type):
        return RESTWorker.REST_CALLS[request_type]

    def stop(self):
        LOG.debug(f'Worker {self._id} is stopping')


def run():
    CSET = settings.get_CONSUMER_CONFIG()
    KSET = settings.get_KAFKA_CONFIG()
    consumer = RESTConsumer(CSET, KSET)  # noqa


if __name__ == "__main__":
    run()
