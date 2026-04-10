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
        route_path = getattr(
            command, '__dw_path__', f'/{command.__name__.lower()}'
        )

        @self.router.post(route_path, response_model=dict)
        async def dynamic_route(
            payload: dict,
            request: Request,
            background_tasks: BackgroundTasks,
        ):
            parsed_command = command.model_validate(payload)
            kwargs = _get_injected_kwargs(
                func,
                dict(request.headers),
                deferred_emitter_factory=(
                    lambda: FastAPIDeferredEmitter(
                        background_tasks=background_tasks,
                    )
                ),
            )
            try:
                func(parsed_command, **kwargs)
            except Forbidden as e:
                raise HTTPException(status_code=403, detail='Forbidden') from e
            return {}

    def generate_query_route(
        self,
        query: Query,
        func: QueryFunctionType,
        query_request: type[QueryRequest] | None = None,
    ):
        path_source = query if query_request is None else query_request
        route_path = getattr(
            path_source, '__dw_path__', f'/{path_source.__name__.lower()}'
        )

        if query_request is None:

            @self.router.get(route_path, response_model=query)
            async def dynamic_route(request: Request):
                kwargs = _get_injected_kwargs(func, dict(request.headers))
                try:
                    return func(**kwargs)
                except Forbidden as e:
                    raise HTTPException(
                        status_code=403, detail='Forbidden'
                    ) from e

            return

        @self.router.get(route_path, response_model=query)
        async def dynamic_route(
            request: Request, payload: query_request = Depends()
        ):
            kwargs = _get_injected_kwargs(func, dict(request.headers))
            try:
                return func(payload, **kwargs)
            except Forbidden as e:
                raise HTTPException(status_code=403, detail='Forbidden') from e

    def get_app(self):
        return self.router
