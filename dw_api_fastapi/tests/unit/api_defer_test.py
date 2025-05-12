from unittest import TestCase
from unittest.mock import patch
from dw_core.cqrs import Command, Event
from dw_api.ports import EndpointGenerator
from dw_events.ports import EventSubscriber
from dw_events.adapters import BasicSubscriber
from dw_api.endpoint import auto_generate_endpoint
from dw_api_fastapi.tests.api_defer_spec import ApiDeferSpec
from dw_api_fastapi.adapters import FastAPIEndpointGenerator
from fastapi import FastAPI
from fastapi.testclient import TestClient
from functools import wraps
import inject
from typing import Callable


def spy(func):
    func.is_called = False

    @wraps(func)
    def wrapper(*args, **kwargs):
        wrapper.is_called = True
        return func(*args, **kwargs)

    return wrapper


class ApiDeferTest(ApiDeferSpec, TestCase):
    def setUp(self):
        self.ports = []
        self.get_ports_patched = patch(
            'dw_api.endpoint.get_ports', wraps=self.get_ports
        )
        self.bgt_add_task_patch = patch(
            'fastapi.BackgroundTasks.add_task', wraps=self.add_task
        )
        self.defered_execution_patched = patch(
            'dw_api_fastapi.defer.FastAPIDeferredEmitter.defer_execution'
        )
        self.deferred_execution_mock = self.defered_execution_patched.start()
        self.bgt_add_task_mock = self.bgt_add_task_patch.start()
        self.get_ports_mock = self.get_ports_patched.start()
        self.port_spies = {}
        self.tasks = []
        self.app = FastAPI()
        self.client = TestClient(self.app)
        self.bs = BasicSubscriber()

        inject.configure(
            lambda binder: binder.bind(EventSubscriber, self.bs), clear=True
        )

    def tearDown(self) -> None:
        self.get_ports_patched.stop()
        self.bgt_add_task_patch.stop()
        self.defered_execution_patched.stop()
        inject.clear()

    def get_ports(self):
        return self.ports

    def add_task(self, func, *args, **kwargs):
        import pdb; pdb.set_trace()
        self.tasks.append([func, args, kwargs])

    def given_port(self, port):
        spyed = spy(port)
        self.port_spies[port] = spyed
        self.ports.append(('any', spyed))

    def given_subscription(
        self, event_class: Event, executer: Callable[[Event], None]
    ):
        spyed = spy(executer)
        self.port_spies[executer] = spyed
        self.bs.subscribe(event_class, spyed)

    def given_generated_endpoints(self):
        inject.configure(
            lambda binder: binder.bind(EventSubscriber, self.bs).bind(
                EndpointGenerator, FastAPIEndpointGenerator()
            ),
            clear=True,
        )
        self.router = auto_generate_endpoint()
        self.app.include_router(self.router)

    def when_call(self, instance):
        path = instance.__class__.__name__.lower()
        payload = instance.model_dump()
        if issubclass(instance.__class__, Command):
            self.response = self.client.post(path, json=payload)

    def assert_execution_deferred(self):
        self.deferred_execution_mock.assert_called()

    def assert_handler_called(self, handler):
        self.assertIn(handler, self.port_spies)
        spyed = self.port_spies[handler]
        self.assertTrue(hasattr(spyed, 'is_called'))
        self.assertTrue(spyed.is_called)

    def assert_task_queue(self):
        self.bgt_add_task_mock.assert_called()
