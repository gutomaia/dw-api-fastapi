from dw_api.ports import (
    CommandFunctionType,
    EndpointGenerator,
    QueryFunctionType,
)
from dw_auth.exceptions import Forbidden
from dw_core.core import get_argument_resolvers
from dw_core.cqrs import Command, Query, QueryRequest
from dw_core.resolver import ResolutionContext, ResolverRegistry
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from dw_api_fastapi.defer import FastAPIDeferredEmitter


def _get_injected_kwargs(func, headers, deferred_emitter_factory=None):
    registry = ResolverRegistry()
    for _, resolver in get_argument_resolvers():
        registry.register(resolver)

    extras: dict = {}
    if deferred_emitter_factory is not None:
        extras['deferred_emitter_factory'] = deferred_emitter_factory

    try:
        return registry.resolve_kwargs(
            func,
            ResolutionContext(headers=headers, extras=extras),
        )
    except PermissionError as e:
        raise HTTPException(status_code=401, detail='Unauthorized') from e
    except Exception as e:
        raise HTTPException(
            status_code=500, detail='Dependency not configured'
        ) from e


class FastAPIEndpointGenerator(EndpointGenerator):
    def __init__(self):
        self.router = APIRouter()

    def generate_command_route(
        self, command: Command, func: CommandFunctionType
    ):
        route_path = f'/{command.__name__.lower()}'
        hints = get_type_hints(func)
        is_deferred = False

        for arg_name, arg_type in hints.items():
            if issubclass(arg_type, DeferredEmitter):
                is_deferred = True
                defer_name = arg_name
                break

        if is_deferred:

            @self.router.post(route_path, response_model=dict)
            async def deferred_dynamic_route(
                payload: dict, background_tasks: BackgroundTasks
            ):
                parsed_command = command.model_validate(payload)
                kwargs = {}
                kwargs[defer_name] = FastAPIDeferredEmitter(
                    background_tasks=background_tasks,
                )
                func(parsed_command, **kwargs)
                return {}

        else:

            @self.router.post(route_path, response_model=dict)
            async def dynamic_route(payload: dict):
                parsed_command = command.model_validate(payload)
                func(parsed_command)
                return {}

    def generate_query_route(self, query: Query, func: QueryFunctionType):
        route_path = f'/{query.__name__.lower()}'

        @self.router.get(route_path, response_model=query)
        async def dynamic_route():
            return func()

    def get_app(self):
        return self.router
