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

from jsonschema.exceptions import ValidationError


@pytest.mark.unit
def test_healthcheck(MockConsumer):
    port = 9013
    settings = {'EXPOSE_PORT': port}
    MockConsumer.serve_api(settings)
    url = 'http://localhost:%s/healthcheck' % port
    r = requests.head(url)
    assert(r.status_code == 200)
    MockConsumer.api.stop()
    try:
        r = requests.head(url)
        assert(r.status_code == 500)
    except requests.exceptions.ConnectionError:
        pass
    else:
        assert(False), 'Healthcheck should be down'


@pytest.mark.unit
def test_init(Consumer):
    port = 9013
    url = 'http://localhost:%s/healthcheck' % port
    r = requests.head(url)
    assert(r.status_code == 200)


@pytest.mark.unit
def test_validate_fail(Consumer, fake_job):
    del fake_job['id']
    with pytest.raises(ValidationError):
        Consumer.validate_job(fake_job)


@pytest.mark.unit
def test_validate_ok(Consumer, fake_job):
    Consumer.validate_job(fake_job)


@pytest.mark.unit
def test_task_crud(Consumer, fake_job):
    _id = fake_job['id']
    _type = 'fakejob'
    assert(Consumer._add_task(fake_job, type=_type) is True)
    job = json.loads(Consumer._get_task(_id, type=_type))
    assert(job['modified'] is not None)
    jobs = list(Consumer._list_tasks(type=_type))
    assert(_id in jobs)
    assert(Consumer._remove_task(_id, type=_type) is True)


@pytest.mark.unit
def test_job_handling(Consumer, fake_job):
    # Add a job and make sure the subscribtion handler picks it up
    _id = fake_job['id']
    assert(Consumer.add_job(fake_job) is True)
    sleep(1)  # Let the pubsub do it's job so we don't get log spam
    job = Consumer.get_job(_id)
    assert(job['modified'] is not None)
    assert(_id in [c[0] for c in Consumer.recent_changes])
    jobs = list(Consumer.list_jobs())
    assert(_id in jobs)
    assert(_id in Consumer.children.keys())
    assert(Consumer.children[_id].status == WorkerStatus.ERR_KAFKA)
    assert(Consumer.remove_job(_id) is True)


@pytest.mark.unit
def test_job_handling_over_api(Consumer, fake_job):
    # Add a job and make sure the subscribtion handler picks it up
    _id = fake_job['id']
    print(f'Handling {_id} over API')
    creds = (Consumer.api.admin_name, Consumer.api.admin_password)
    url = 'http://localhost:9013/jobs/'
    add = url + 'add'
    res = requests.post(add, json=fake_job, auth=creds)
    assert(res.status_code is 200)
    sleep(1)  # Let the pubsub do it's job so we don't get log spam
    get = url + f'get?id={_id}'
    res = requests.get(get, auth=creds)
    assert(res.status_code is 200)
    job = res.json()
    assert(job['modified'] is not None)
    assert(_id in [c[0] for c in Consumer.recent_changes])
    _list = url + 'list'
    res = requests.get(_list, auth=creds)
    assert(res.status_code is 200)
    jobs = res.json()
    assert(_id in jobs)
    assert(_id in Consumer.children.keys())
    assert(Consumer.children[_id].status == WorkerStatus.ERR_KAFKA)
    rem = url + f'delete?id={_id}'
    res = requests.get(rem, auth=creds)
    assert(res.status_code is 200)


@pytest.mark.unit
def test_job_update_handling(Consumer, fake_job):
    # Add a job and make sure the subscribtion handler picks it up
    _id = fake_job['id']
    print(f'Handling {_id} in CODE')
    assert(Consumer.add_job(fake_job) is True)
    sleep(1)  # Let the pubsub do it's job so we don't get log spam
    job = Consumer.get_job(_id)
    assert(job['modified'] is not None)
    new_job = dict(fake_job)
    new_job['type'] = 'GET'
    assert(Consumer.add_job(new_job) is True)
    # sleep(3)  # let update finish before deleting
    assert(Consumer.remove_job(_id) is True)


@pytest.mark.unit
def test_worker_process_datamap(Worker):
    res = Worker.process_data_map(data_map, data)
    assert(res == mapping_result)


@responses.activate
@pytest.mark.unit
def test_make_get_request(Worker, fake_job):
    assert(Worker.status == WorkerStatus.ERR_CONFIG)
    job = dict(fake_job)
    job['type'] = 'GET'
    full_url = job['url'].format(id=fake_job_msg['id'])
    msg = {'msg': fake_job_msg}
    responses.add(responses.GET, full_url,
                  status=201,
                  match_querystring=False)
    mapped_data = Worker.process_data_map(job['datamap'], msg)
    res = Worker.make_request(mapped_data, job)
    for param in job['query_params']:
        assert(param in res.url)
    assert (res.status_code == 201)


@responses.activate
@pytest.mark.unit
def test_make_post_request(Worker, fake_job):
    job = dict(fake_job)
    full_url = job['url'].format(id=fake_job_msg['id'])
    msg = {'msg': fake_job_msg}
    responses.add(responses.POST, full_url,
                  status=201,
                  match_querystring=False)
    mapped_data = Worker.process_data_map(job['datamap'], msg)
    res = Worker.make_request(mapped_data, job)
    assert (res.status_code == 201)


@responses.activate
@pytest.mark.unit
def test_make_basic_request(Worker, fake_job):
    creds = {'user': 'someuser', 'password': 'pw'}
    job = dict(fake_job)
    job['basic_auth'] = creds

    def check_creds(request):
        assert('Authorization' in request.headers)
        return (200, request.headers, json.dumps({}))

    full_url = job['url'].format(id=fake_job_msg['id'])
    msg = {'msg': fake_job_msg}

    responses.add_callback(responses.POST, full_url,
                           content_type='application/json',
                           callback=check_creds,
                           match_querystring=False)
    mapped_data = Worker.process_data_map(job['datamap'], msg)
    res = Worker.make_request(mapped_data, job)
    assert (res.status_code == 200)


@responses.activate
@pytest.mark.unit
def test_make_token_request(Worker, fake_job):
    token = 'sometoken'
    job = dict(fake_job)
    job['token'] = token

    def check_creds(request):
        assert('access_token' in request.headers['Authorization'])
        return (200, request.headers, json.dumps({}))

    full_url = job['url'].format(id=fake_job_msg['id'])
    msg = {'msg': fake_job_msg}

    responses.add_callback(responses.POST, full_url,
                           content_type='application/json',
                           callback=check_creds,
                           match_querystring=False)
    mapped_data = Worker.process_data_map(job['datamap'], msg)
    res = Worker.make_request(mapped_data, job)
    assert (res.status_code == 200)


@pytest.mark.unit
def test_job_stop_on_shutdown(Consumer, fake_job):
    # Add a job and make sure the subscribtion handler picks it up
    _id = fake_job['id']
    assert(Consumer.add_job(fake_job) is True)
    sleep(1)  # Let the pubsub do it's job so we don't get log spam
    job = Consumer.get_job(_id)
    assert(job['modified'] is not None)
    new_job = dict(fake_job)
    new_job['type'] = 'GET'
    assert(Consumer.add_job(new_job) is True)
    sleep(1)  # let update finish before deleting
    assert(len(Consumer.children) > 0)
