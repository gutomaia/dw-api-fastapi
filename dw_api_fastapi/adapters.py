from dw_api.exceptions import ApiError
from dw_api.exceptions import Forbidden as ApiForbidden
from dw_api.executor import RouteExecutor, route_path
from dw_api.ports import (
    CommandFunctionType,
    EndpointGenerator,
    QueryFunctionType,
)
from dw_auth.exceptions import Forbidden
from dw_core.cqrs import Command, Query, QueryRequest
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from dw_api_fastapi.defer import FastAPIDeferredEmitter


class FastAPIEndpointGenerator(EndpointGenerator):
    def __init__(self, resolvers=None):
        self.router = APIRouter()
        self.executor = RouteExecutor(
            error_map=[(Forbidden, ApiForbidden)],
            resolvers=resolvers,
        )

    def generate_command_route(
        self, command: Command, func: CommandFunctionType
    ):
        @self.router.post(route_path(command), response_model=dict)
        async def dynamic_route(
            payload: dict,
            request: Request,
            background_tasks: BackgroundTasks,
        ):
            extras = {
                'deferred_emitter_factory': (
                    lambda: FastAPIDeferredEmitter(
                        background_tasks=background_tasks,
                    )
                )
            }
            try:
                return self.executor.execute_command(
                    command,
                    func,
                    payload,
                    dict(request.headers),
                    extras=extras,
                )
            except ApiError as e:
                raise HTTPException(
                    status_code=e.status_code, detail=e.detail
                ) from e

    def generate_query_route(
        self,
        query: Query,
        func: QueryFunctionType,
        query_request: type[QueryRequest] | None = None,
    ):
        path_source = query if query_request is None else query_request

        if query_request is None:

            @self.router.get(route_path(path_source), response_model=query)
            async def dynamic_route(request: Request):
                try:
                    return self.executor.execute_query(
                        func, dict(request.headers)
                    )
                except ApiError as e:
                    raise HTTPException(
                        status_code=e.status_code, detail=e.detail
                    ) from e

            return

        @self.router.get(route_path(path_source), response_model=query)
        async def dynamic_route(
            request: Request, payload: query_request = Depends()
        ):
            try:
                return self.executor.execute_query(
                    func,
                    dict(request.headers),
                    query_request=query_request,
                    params=payload.model_dump(),
                )
            except ApiError as e:
                raise HTTPException(
                    status_code=e.status_code, detail=e.detail
                ) from e

    def get_app(self):
        return self.router
