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
# import requests

from datetime import datetime
import json
from jsonschema import validate
import redis


from . import settings
from .healthcheck import HealthcheckServer

EXCLUDED_TOPICS = ['__confluent.support.metrics']


class RESTConsumer(object):

    def __init__(self, CSET, KSET):
        self.serve_healthcheck(CSET['EXPOSE_PORT'])
        self.redis = redis.Redis(
            host=CSET['REDIS_HOST'],
            port=CSET['REDIS_PORT'],
            db=CSET['REDIS_DB'],
            encoding="utf-8",
            decode_responses=True
        )
        self.schema = self.load_schema()

    def serve_healthcheck(self, port):
        self.healthcheck = HealthcheckServer(port)
        self.healthcheck.start()

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
            raise ValueError(f'No job with id {_id}')
        return task

    def _list_tasks(self, type):
        # jobs as a generator
        key_identifier = f'_{type}:*'
        for i in self.redis.scan_iter(key_identifier):
            yield str(i).split(key_identifier[:-1])[1]

    def load_schema(self):
        with open('./app/job_schema.json') as f:
            return json.load(f)

    def validate_job(self, job):
        validate(job, self.schema)  # Throws ValidationErrors

    def _add_job(self, job):
        self.validate_job(job)
        return self._add_task(job, type='job')

    def _job_exists(self, _id):
        return self._task_exists(_id, type='job')

    def _remove_job(self, _id):
        return self._remove_task(_id, type='job')

    def _get_job(self, _id):
        return json.loads(self._get_task(_id, type='job'))

    def _list_jobs(self):
        return self._list_tasks(type='job')


def run():
    CSET = settings.get_CONSUMER_CONFIG()
    KSET = settings.get_KAFKA_CONFIG()
    consumer = RESTConsumer(CSET, KSET)  # noqa


if __name__ == "__main__":
    run()
