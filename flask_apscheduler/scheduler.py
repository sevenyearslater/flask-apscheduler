# Copyright 2015 Vinicius Chiele. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""APScheduler implementation."""

import logging
import socket

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask
from . import views
from .utils import fix_job_def

LOGGER = logging.getLogger('flask_apscheduler')


class APScheduler(object):
    """Provides a scheduler integrated to Flask."""

    def __init__(self, scheduler=None, app=None):
        self.__scheduler = scheduler or BackgroundScheduler()
        self.__allowed_hosts = ['*']
        self.__host_name = socket.gethostname().lower()
        self.__views_enabled = False

        self.app = None

        if app:
            self.init_app(app)

    @property
    def host_name(self):
        """Gets the host name."""
        return self.__host_name

    @property
    def allowed_hosts(self):
        """Gets the allowed hosts."""
        return self.__allowed_hosts

    @property
    def running(self):
        """Gets true whether the scheduler is running."""
        return self.scheduler.running

    @property
    def scheduler(self):
        """Gets the base scheduler."""
        return self.__scheduler

    def init_app(self, app):
        """Initializes the APScheduler with a Flask application instance."""

        if not isinstance(app, Flask):
            raise TypeError('app must be a Flask application')

        self.app = app
        self.app.apscheduler = self

        self.__load_config()
        self.__load_jobs()

        if self.__views_enabled:
            self.__load_views()

    def start(self):
        """Starts the scheduler."""

        if not self.allowed_hosts:
            LOGGER.debug('No server allowed to start the scheduler.')

        if self.host_name not in self.allowed_hosts and '*' not in self.allowed_hosts:
            LOGGER.debug('Host name %s is not allowed to start the APScheduler. Servers allowed: %s' %
                         (self.host_name, ','.join(self.allowed_hosts)))
            return

        self.__scheduler.start()

    def shutdown(self, wait=True):
        """
        Shuts down the scheduler. Does not interrupt any currently running jobs.

        :param bool wait: ``True`` to wait until all currently executing jobs have finished
        :raises SchedulerNotRunningError: if the scheduler has not been started yet
        """

        self.__scheduler.shutdown(wait)

    def add_job(self, id, func, **kwargs):
        """
        Adds the given job to the job list and wakes up the scheduler if it's already running.

        :param str job_id: explicit identifier for the job (for modifying it later)
        :param func: callable (or a textual reference to one) to run at the given time
        """

        if not id:
            raise Exception('Argument id cannot be None.')

        if not func:
            raise Exception('Argument func cannot be None.')

        name = kwargs.get('name') or id

        fix_job_def(kwargs)

        job = self.__scheduler.add_job(func, id=id, name=name, **kwargs)

        return job

    def delete_job(self, id, jobstore=None):
        """
        Removes a job, preventing it from being run any more.

        :param str id: the identifier of the job
        :param str jobstore: alias of the job store that contains the job
        """

        self.__scheduler.remove_job(id, jobstore)

    def modify_job(self, id, jobstore=None, **kwargs):
        """
        Modifies the properties of a single job. Modifications are passed to this method as extra keyword arguments.

        :param str id: the identifier of the job
        :param str jobstore: alias of the job store that contains the job
        """

        if not id:
            raise Exception('Argument id cannot be None or empty.')

        fix_job_def(kwargs)

        self.__scheduler.modify_job(id, jobstore, **kwargs)

        job = self.__scheduler.get_job(id, jobstore)

        return job

    def pause_job(self, id, jobstore=None):
        """
        Causes the given job not to be executed until it is explicitly resumed.

        :param str id: the identifier of the job
        :param str jobstore: alias of the job store that contains the job
        """

        self.__scheduler.pause_job(id, jobstore)

    def resume_job(self, id, jobstore=None):
        """
        Resumes the schedule of the given job, or removes the job if its schedule is finished.

        :param str id: the identifier of the job
        :param str jobstore: alias of the job store that contains the job
        """
        self.__scheduler.resume_job(id, jobstore)

    def run_job(self, id, jobstore=None):
        job = self.__scheduler.get_job(id, jobstore)

        if not job:
            raise LookupError(id)

        job.func(*job.args, **job.kwargs)

    def __load_config(self):
        """Loads the configuration from the Flask configuration."""

        options = dict()

        job_stores = self.app.config.get('SCHEDULER_JOBSTORES')
        if job_stores:
            options['jobstores'] = job_stores

        executors = self.app.config.get('SCHEDULER_EXECUTORS')
        if executors:
            options['executors'] = executors

        job_defaults = self.app.config.get('SCHEDULER_JOB_DEFAULTS')
        if job_defaults:
            options['job_defaults'] = job_defaults

        timezone = self.app.config.get('SCHEDULER_TIMEZONE')
        if timezone:
            options['timezone'] = timezone

        self.__scheduler.configure(**options)

        self.__allowed_hosts = self.app.config.get('SCHEDULER_ALLOWED_HOSTS', self.__allowed_hosts)
        self.__views_enabled = self.app.config.get('SCHEDULER_VIEWS_ENABLED', self.__views_enabled)

    def __load_jobs(self):
        """Loads the job definitions from the Flask configuration."""

        jobs = self.app.config.get('SCHEDULER_JOBS')

        if not jobs:
            jobs = self.app.config.get('JOBS')

        if jobs:
            for job in jobs:
                self.add_job(**job)

    def __load_views(self):
        """Adds the routes for the scheduler UI."""

        self.app.add_url_rule('/scheduler', 'get_scheduler_info', views.get_scheduler_info)
        self.app.add_url_rule('/scheduler/jobs', 'add_job', views.add_job, methods=['POST'])
        self.app.add_url_rule('/scheduler/jobs', 'get_jobs', views.get_jobs)
        self.app.add_url_rule('/scheduler/jobs/<job_id>', 'get_job', views.get_job)
        self.app.add_url_rule('/scheduler/jobs/<job_id>', 'delete_job', views.delete_job, methods=['DELETE'])
        self.app.add_url_rule('/scheduler/jobs/<job_id>', 'update_job', views.update_job, methods=['PATCH'])
        self.app.add_url_rule('/scheduler/jobs/<job_id>/pause', 'pause_job', views.pause_job, methods=['POST'])
        self.app.add_url_rule('/scheduler/jobs/<job_id>/resume', 'resume_job', views.resume_job, methods=['POST'])
        self.app.add_url_rule('/scheduler/jobs/<job_id>/run', 'run_job', views.run_job, methods=['POST'])
