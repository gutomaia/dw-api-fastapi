from functools import wraps
from unittest import TestCase
from unittest.mock import patch

import inject
from dw_api.endpoint import auto_generate_endpoint
from dw_api.ports import EndpointGenerator
from dw_api.tests.generate_endpoint_spec import GenerateEndpointSpec
from dw_core.cqrs import Command
from dw_events.adapters import BasicSubscriber
from dw_events.ports import EventSubscriber
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dw_api_fastapi.adapters import FastAPIEndpointGenerator


def spy(func):
    func.is_called = False

    @wraps(func)
    def wrapper(*args, **kwargs):
        wrapper.is_called = True
        return func(*args, **kwargs)

    return wrapper


class GenerateFastAPIEndpointTest(GenerateEndpointSpec, TestCase):
    def setUp(self) -> None:
        self.ports = []
        self.get_ports_patched = patch(
            'dw_api.endpoint.get_ports', wraps=self.get_ports
        )
        self.get_ports_mock = self.get_ports_patched.start()
        self.port_spies = {}
        self.app = FastAPI()
        self.client = TestClient(self.app)
        self.bs = BasicSubscriber()
        inject.configure(
            lambda binder: binder.bind(EventSubscriber, self.bs), clear=True
        )

    def tearDown(self) -> None:
        self.get_ports_patched.stop()
        inject.clear()

    def get_ports(self):
        return self.ports

    def given_port(self, port):
        spyed = spy(port)
        self.port_spies[port] = spyed
        self.ports.append(('any', spyed))

    def when_auto_generate_endpoints(self):
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

    def assert_endpoints_length(self, size):
        self.assertEqual(len(self.router.routes), size)

    def assert_command_called(self, command):
        spyed = self.port_spies[command]
        self.assertTrue(hasattr(spyed, 'is_called'))
        self.assertTrue(spyed.is_called)

    def assert_result_code(self, code):
        self.assertTrue(hasattr(self, 'response'))
        self.assertEqual(self.response.status_code, code)
