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

import pytest
import requests  # noqa
from uuid import uuid4

from app.main import RESTConsumer
from app import settings

kafka_server = "kafka-test:29099"


# We can use 'mark' distinctions to chose which tests are run and which assets are built
# @pytest.mark.integration
# @pytest.mark.unit
# When possible use fixtures for reusable test assets
# @pytest.fixture(scope="session")


class _MockConsumer(RESTConsumer):

    def __init__(self):
        self.killed = False


@pytest.mark.integration
@pytest.mark.unit
@pytest.fixture(scope="function")
def MockConsumer():
    consumer = _MockConsumer()
    consumer.schema = consumer.load_schema()
    return consumer


@pytest.mark.integration
@pytest.mark.unit
@pytest.fixture(scope="module")
def Consumer():
    CSET = settings.get_CONSUMER_CONFIG()
    KSET = settings.get_KAFKA_CONFIG()
    consumer = RESTConsumer(CSET, KSET)  # noqa
    yield consumer
    consumer.healthcheck.stop()


@pytest.mark.integration
@pytest.mark.unit
@pytest.fixture(scope="function")
def fake_job():
    return {
        'id': str(uuid4()),
        'owner': 'the owner',
        'type': 'POST',
        'topic': [
            'a',
            'b'
        ],
        'datamap': {
            'key1': 'val1',
            'key2': 'val2'
        },
        'url': 'http://someurl',
        'query_params': [
            'key1',
            'key2'
        ],
        'json_body': [
            'key1',
            'key2'
        ]
    }
