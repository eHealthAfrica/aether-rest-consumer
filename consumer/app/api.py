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

from flask import Flask, Response, request, jsonify
from gevent.pool import Pool
from gevent.pywsgi import WSGIServer


class APIServer(object):

    def __init__(self, consumer, settings):
        self.settings = settings

    def serve(self):
        self.app = Flask('RESTConsumer')  # noqa
        try:
            handler = self.app.logger.handlers[0]
        except IndexError:
            handler = logging.StreamHandler()
            self.app.logger.addHandler(handler)
        finally:
            log_level = logging.getLevelName(self.settings
                                         .get('log_level', 'DEBUG'))
            self.app.logger.setLevel(log_level)

        self.app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        pool_size = self.settings.get('max_connections', 3)
        server_ip = self.settings.get('server_ip', "")
        server_port = int(self.settings.get('EXPOSE_PORT', 9013))
        self.worker_pool = Pool(pool_size)
        self.http = WSGIServer(
            (server_ip, server_port),
            self.app.wsgi_app, spawn=self.worker_pool
        )
        self.http.start()

    # Flask Functions

    def add_endpoints(self):
        # URLS configured here
        self.register('jobs/add', self.add_job)
        self.register('jobs/delete', self.remove_job)
        self.register('jobs/update', self.add_job)
        self.register('jobs/validate', self.validate_job)
        self.register('jobs/get', self.get_job)
        self.register('jobs/list', self.list_jobs)
        self.register('healtcheck', self.request_healthcheck)

    def register(self, route_name, fn):
        self.app.add_url_rule('/%s' % route_name, route_name, view_func=fn)

    # Basic Auth implementation

    def check_auth(self, username, password):
        return username == self.admin_name and password == self.admin_password

    def request_authentication(self):
        return Response('Bad Credentials', 401,
                        {'WWW-Authenticate': 'Basic realm="Login Required"'})

    def requires_auth(f):
        @wraps(f)
        def decorated(self, *args, **kwargs):
            auth = request.authorization
            if not auth or not self.check_auth(auth.username, auth.password):
                return self.request_authentication()
            return f(self, *args, **kwargs)
        return decorated

    # Exposed endpoints

    def request_healthcheck(self):
        with self.app.app_context():
            return Response({"healthy": True})

    @requires_auth
    def add_job(self):
        return self.handle_job_crud(request, 'CREATE')

    @requires_auth
    def remove_job(self):
        return self.handle_job_crud(request, 'DELETE')

    @requires_auth
    def get_job(self):
        return self.handle_job_crud(request, 'READ')

    @requires_auth
    def list_jobs(self):
        with self.app.app_context():
            return jsonify(self.consumer.list_jobs())

    @requires_auth
    def validate_job(self):
        res = self.consumer.validate_job(**request.args)
        with self.app.app_context():
            return jsonify({'valid' : res})

    def handle_job_crud(self, request, _type):
        _id = request.args.get('id', None)
        if _type == 'CREATE':
            response = jsonify(self.consumer.add_job(**request.args))
        if _type == 'DELETE':
            response = jsonify(self.consumer.remove_job(_id))
        if _type == 'READ':
            response = jsonify(self.consumer.get_job(_id))
        with self.app.app_context():
            return response
