from functools import wraps
from unittest import TestCase
from unittest.mock import patch

import inject
from dw_api.endpoint import auto_generate_endpoint
from dw_api.ports import EndpointGenerator
from dw_auth.domain import AnonymousPrincipal, AuthenticatedPrincipal
from dw_auth.ports import Authenticator
from dw_core.cqrs import Command, Query
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


class HeaderAuthenticator(Authenticator):
    def authenticate(self, headers):
        if not headers:
            return AnonymousPrincipal()
        token = headers.get('authorization') or headers.get('Authorization')
        if token:
            return AuthenticatedPrincipal(subject='user-1', provider='test')
        return AnonymousPrincipal()


class AuthenticationFastAPITest(TestCase):
    def setUp(self) -> None:
        self.ports = []
        self.get_ports_patched = patch(
            'dw_api.endpoint.get_ports', wraps=self.get_ports
        )
        self.get_ports_patched.start()
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
            lambda binder: binder.bind(EventSubscriber, self.bs)
            .bind(EndpointGenerator, FastAPIEndpointGenerator())
            .bind(Authenticator, HeaderAuthenticator()),
            clear=True,
        )
        self.router = auto_generate_endpoint()
        self.app.include_router(self.router)

    def test_authenticated_principal_is_injected_for_command(self):
        class WhoAmI(Command):
            pass

        def whoami(cmd: WhoAmI, principal: AuthenticatedPrincipal) -> None:
            assert principal.subject == 'user-1'

        self.given_port(whoami)
        self.when_auto_generate_endpoints()

        payload = WhoAmI().model_dump()
        self.response = self.client.post(
            '/whoami',
            json=payload,
            headers={'Authorization': 'Bearer token'},
        )

        self.assertEqual(self.response.status_code, 200)
        self.assertTrue(self.port_spies[whoami].is_called)

    def test_unauthorized_when_authenticated_principal_required_for_command(
        self,
    ):
        class WhoAmI(Command):
            pass

        def whoami(cmd: WhoAmI, principal: AuthenticatedPrincipal) -> None:
            raise RuntimeError('must not be called')

        self.given_port(whoami)
        self.when_auto_generate_endpoints()

        payload = WhoAmI().model_dump()
        self.response = self.client.post('/whoami', json=payload)

        self.assertEqual(self.response.status_code, 401)
        self.assertFalse(self.port_spies[whoami].is_called)

    def test_authenticated_principal_is_injected_for_query(self):
        class WhoAmIQuery(Query):
            subject: str

        def whoami(principal: AuthenticatedPrincipal) -> WhoAmIQuery:
            return WhoAmIQuery(subject=principal.subject)

        self.given_port(whoami)
        self.when_auto_generate_endpoints()

        self.response = self.client.get(
            '/whoamiquery',
            headers={'Authorization': 'Bearer token'},
        )

        self.assertEqual(self.response.status_code, 200)
        self.assertEqual(self.response.json().get('subject'), 'user-1')
