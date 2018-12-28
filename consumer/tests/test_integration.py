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

from . import *  # get all test assets from test/__init__.py

# Test Suite contains both unit and integration tests
# Unit tests can be run on their own from the root directory
# enter the bash environment for the version of python you want to test
# for example for python 3
# `docker-compose run consumer-sdk-test bash`
# then start the unit tests with
# `pytest -m unit`
# to run integration tests / all tests run the test_all.sh script from the /tests directory.


@pytest.mark.integration
def test_healthcheck():
    assert(True)


@responses.activate
@pytest.mark.integration
def test_add_get_job(Consumer):
    job = integration_job
    _id = job['id']
    callback, counter = generate_callback(job)
    full_url = job['url'].format(id=_id)
    responses.add_callback(responses.POST, full_url,
                           callback=callback,
                           match_querystring=False)
    assert(counter == 0)
    assert(Consumer.add_job(integration_job) is True)
    sleep(1)
    while Consumer.children[_id].status is not WorkerStatus.RUNNING:
        sleep(1)
        print(f'Waiting for status: {Consumer.children[_id].status}')
    while counter < 40:
        print(f'progress : {counter/40}')
        sleep(1)
