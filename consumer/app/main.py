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

from . import settings
from .healthcheck import HealthcheckServer

EXCLUDED_TOPICS = ['__confluent.support.metrics']


class RESTConsumer(object):

    def __init__(self):
        self.serve_healthcheck(CSET['EXPOSE_PORT'])

    def serve_healthcheck(self, port):
        self.healthcheck = HealthcheckServer(port)
        self.healthcheck.start()


def run():
    global KSET, CSET
    CSET = settings.get_CONSUMER_CONFIG()
    KSET = settings.get_KAFKA_CONFIG()
    consumer = RESTConsumer()  # noqa


if __name__ == "__main__":
    run()
