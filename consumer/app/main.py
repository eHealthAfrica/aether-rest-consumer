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
            db=CSET['REDIS_DB']
        )
        self.schema = self.load_schema()

    def serve_healthcheck(self, port):
        self.healthcheck = HealthcheckServer(port)
        self.healthcheck.start()

    def validate_job(self, job):
        validate(job, self.schema)  # Throws ValidationErrors

    def _add_job(self, job):
        self.validate_job(job)
        key = job['id']
        job['modified'] = datetime.now().isoformat()
        self.redis.set(key, job)

    def _job_exists(self, _id):
        if self.redis.exists(_id):
            return True
        return False

    def _remove_job(self, _id):
        return self.redis.delete(_id)

    def _get_job(self, _id):
        return self.redis.get(_id)

    def _list_jobs(self):
        # jobs as a generator
        key_identifier = '_job:*'
        for i in self.redis.scan_iter(key_identifier):
            yield i

    def load_schema(self):
        with open('./app/job_schema.json') as f:
            return json.load(f)


def run():
    CSET = settings.get_CONSUMER_CONFIG()
    KSET = settings.get_KAFKA_CONFIG()
    consumer = RESTConsumer(CSET, KSET)  # noqa


if __name__ == "__main__":
    run()
