from unittest import TestCase
from unittest.mock import patch

import inject
from dw_api.endpoint import auto_generate_endpoint
from dw_api.ports import EndpointGenerator
from dw_api.tests.execute_query_spec import ExecuteQuerySpec
from dw_events.adapters import BasicSubscriber
from dw_events.ports import EventSubscriber
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dw_api_fastapi.adapters import FastAPIEndpointGenerator


class ExecuteQueryFastAPITest(ExecuteQuerySpec, TestCase):
    def setUp(self) -> None:
        self.ports = []
        self.get_ports_patched = patch(
            'dw_api.endpoint.get_ports', wraps=self.get_ports
        )
        self.get_ports_patched.start()

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
        self.ports.append(('any', port))

    def when_execute_query(self, path: str, *, params=None, headers=None):
        inject.configure(
            lambda binder: binder.bind(EventSubscriber, self.bs).bind(
                EndpointGenerator, FastAPIEndpointGenerator()
            ),
            clear=True,
        )
        router = auto_generate_endpoint()
        self.app.include_router(router)

        self.response = self.client.get(
            path, params=params or {}, headers=headers or {}
        )
        self.assertEqual(self.response.status_code, 200)
        self.response_json = self.response.json()

    def assert_response_has(self, **kwargs):
        for key, expected in kwargs.items():
            parts = key.split('__')
            value = self.response_json
            for part in parts:
                if isinstance(value, list):
                    value = value[int(part)]
                else:
                    value = value[part]
            self.assertEqual(value, expected)
