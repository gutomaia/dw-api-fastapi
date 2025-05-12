from typing import get_type_hints

from dw_api.ports import (
    CommandFunctionType,
    EndpointGenerator,
    QueryFunctionType,
)
from dw_core.cqrs import Command, Query
from dw_events.ports import DeferredEmitter
from fastapi import APIRouter, BackgroundTasks

from dw_api_fastapi.defer import FastAPIDeferredEmitter


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
