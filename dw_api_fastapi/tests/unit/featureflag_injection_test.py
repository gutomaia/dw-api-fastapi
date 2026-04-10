from typing import Annotated
from unittest import TestCase
from unittest.mock import patch

import inject
from dw_api.endpoint import auto_generate_endpoint
from dw_api.ports import EndpointGenerator
from dw_auth.domain import AnonymousPrincipal, AuthenticatedPrincipal
from dw_auth.ports import Authenticator
from dw_core.cqrs import Command
from dw_events.adapters import BasicSubscriber
from dw_events.ports import EventSubscriber
from dw_featureflag.client import FeatureFlags
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


class FeatureFlagInjectionFastAPITest(TestCase):
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

    def when_auto_generate_endpoints(self):
        inject.configure(
            lambda binder: binder.bind(EventSubscriber, self.bs)
            .bind(EndpointGenerator, FastAPIEndpointGenerator())
            .bind(Authenticator, HeaderAuthenticator())
            .bind(FeatureFlagProvider, self.provider),
            clear=True,
        )
        self.router = auto_generate_endpoint()
        self.app.include_router(self.router)

    def test_featureflags_is_injected_and_isolated_by_subject(self):
        class WhoAmIWithFlags(Command):
            ok: bool

        flag = FeatureFlag[bool](key='new-feature', default=False)
        self.provider.set_override('user-1', flag, True)

        seen: list[bool] = []

        def handler(
            cmd: WhoAmIWithFlags,
            principal: AuthenticatedPrincipal,
            ff: FeatureFlags,
        ) -> None:
            assert principal.subject in {'user-1', 'user-2'}
            seen.append(ff.get(flag))

        self.given_port(handler)
        self.when_auto_generate_endpoints()

        payload = WhoAmIWithFlags(ok=True).model_dump()

        r1 = self.client.post(
            '/whoamiwithflags',
            json=payload,
            headers={'Authorization': 'user-1'},
        )
        self.assertEqual(r1.status_code, 200)

        r2 = self.client.post(
            '/whoamiwithflags',
            json=payload,
            headers={'Authorization': 'user-2'},
        )
        self.assertEqual(r2.status_code, 200)

        self.assertEqual(seen, [True, False])

    def test_annotated_flag_value_is_injected(self):
        class WhoAmIWithFlagValue(Command):
            ok: bool

        flag = FeatureFlag[bool](key='new-feature', default=False)
        NewFeature = Annotated[bool, flag]

        self.provider.set_override('user-1', flag, True)

        seen: list[bool] = []

        def handler(
            cmd: WhoAmIWithFlagValue,
            principal: AuthenticatedPrincipal,
            new_feature: NewFeature,
        ) -> None:
            assert principal.subject == 'user-1'
            seen.append(new_feature)

        self.given_port(handler)
        self.when_auto_generate_endpoints()

        payload = WhoAmIWithFlagValue(ok=True).model_dump()
        r = self.client.post(
            '/whoamiwithflagvalue',
            json=payload,
            headers={'Authorization': 'user-1'},
        )

        self.assertEqual(r.status_code, 200)
        self.assertEqual(seen, [True])
