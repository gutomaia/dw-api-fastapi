from unittest import TestCase
from unittest.mock import patch

import inject
from dw_api.endpoint import auto_generate_endpoint
from dw_api.ports import EndpointGenerator
from dw_api.tests.resolve_feature_flag_spec import ResolveFeatureFlagSpec
from dw_auth.domain import AnonymousPrincipal, AuthenticatedPrincipal
from dw_auth.ports import Authenticator
from dw_events.adapters import BasicSubscriber
from dw_events.ports import EventSubscriber
from dw_featureflag.domain import FeatureFlag
from dw_featureflag.ports import FeatureFlagProvider
from dw_featureflag.tests.inmemory_provider import InMemoryFeatureFlagProvider
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dw_api_fastapi.adapters import FastAPIEndpointGenerator


class HeaderAuthenticator(Authenticator):
    def authenticate(self, headers):
        if not headers:
            return AnonymousPrincipal()
        token = headers.get('authorization') or headers.get('Authorization')
        if token:
            return AuthenticatedPrincipal(subject=token, provider='test')
        return AnonymousPrincipal()


class ResolveFeatureFlagFastAPITest(ResolveFeatureFlagSpec, TestCase):
    def setUp(self) -> None:
        self.ports = []
        self.get_ports_patched = patch(
            'dw_api.endpoint.get_ports', wraps=self.get_ports
        )
        self.get_ports_patched.start()

        self.app = FastAPI()
        self.client = TestClient(self.app)

        self.bs = BasicSubscriber()
        self.provider = InMemoryFeatureFlagProvider()

        inject.configure(
            lambda binder: binder.bind(EventSubscriber, self.bs),
            clear=True,
        )

    def tearDown(self) -> None:
        self.get_ports_patched.stop()
        inject.clear()

    def get_ports(self):
        return self.ports

    def given_port(self, port):
        self.ports.append(('any', port))

    def given_feature_flag(
        self,
        flag: FeatureFlag,
        flag_value,
        subject: str | None = None,
    ):
        self.provider.set_override(subject, flag, flag_value)

    def _generate_endpoints(self):
        inject.configure(
            lambda binder: binder.bind(EventSubscriber, self.bs)
            .bind(EndpointGenerator, FastAPIEndpointGenerator())
            .bind(Authenticator, HeaderAuthenticator())
            .bind(FeatureFlagProvider, self.provider),
            clear=True,
        )
        router = auto_generate_endpoint()
        self.app.include_router(router)

    def when_execute_query(self, path: str, *, params=None, headers=None):
        self._generate_endpoints()

        self.response = self.client.get(
            path,
            params=params or {},
            headers=headers or {'Authorization': 'user-1'},
        )
        self.assertEqual(self.response.status_code, 200)
        self.response_json = self.response.json()

    def when_execute_command(self, path: str, *, payload=None, headers=None):
        self._generate_endpoints()

        self.response = self.client.post(
            path,
            json=payload or {},
            headers=headers or {'Authorization': 'user-1'},
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
