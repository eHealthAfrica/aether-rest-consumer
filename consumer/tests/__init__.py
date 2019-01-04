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

import json  # noqa
import pytest
import responses  # noqa
import requests  # noqa
from time import sleep  # noqa
from uuid import uuid4

from app.main import RESTConsumer, RESTWorker, WorkerStatus  # noqa
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
    sleep(2)
    consumer.stop()


@pytest.mark.integration
@pytest.mark.unit
@pytest.fixture(scope="function")
def Worker():
    KSET = settings.get_KAFKA_CONFIG()
    worker = RESTWorker('test_worker_no_config', {}, KSET)  # noqa
    yield worker
    worker.stop()


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
            'id': '$.msg.id',
            'key1': '$.msg.val1',
            'key2': '$.msg.val2'
        },
        'url': 'http://someurl.com/api/{id}/',
        'query_params': [
            'key1',
            'key2'
        ],
        'json_body': [
            'key1',
            'key2'
        ]
    }


@pytest.mark.integration
def generate_callback(job):
    counter = []

    def cb(request):
        nonlocal counter
        counter.append(1)
        return (201, {}, json.dumps({'counter': sum(counter)}))
    return cb, counter


fake_job_msg = {
    'id': 'theid',
    'val1': 'value1',
    'val2': 'value2'
}


data = {
    '_id': 'an_id',
    'a_list': [1, 2, 3, 4],
    'b_list': {
        'a': 1,
        'b': 'two',
        'c': '3po'
    },
    'c_item': 1.2,
    'd_item': False
}

data_map = {
    '_id': '$.id',
    'whole_list': '$.a_list',
    'list_item': '$.a.list[0]',
    'b_dot_a': '$.b_list.a',
    'whole_dict': '$.b_list',
    'number': '$.c_item',
    'boolean': '$.d_item'
}

mapping_result = {
    'whole_list': [1, 2, 3, 4],
    'b_dot_a': 1,
    'whole_dict': {'a': 1, 'b': 'two', 'c': '3po'},
    'number': 1.2,
    'boolean': False
}

integration_job = {
    'id': str(uuid4()),
    'owner': 'the owner',
    'type': 'POST',
    'topic': [
            'Person'
    ],
    'datamap': {
        'type': '$.schema.name',
        'doc': '$.schema.doc',
        'id': '$.msg.id',
        'age': '$.msg.age'
    },
    'url': 'http://someurl.com/api/{type}/',
    'query_params': [
        'id',
        'age'
    ],
    'json_body': [
        'type',
        'doc',
        'id',
        'age'
    ]
}
