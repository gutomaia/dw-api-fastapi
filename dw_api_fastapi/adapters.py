from dw_api.ports import CommandFunctionType, EndpointGenerator, QueryFunctionType
from dw_core.cqrs import Command, Query
from fastapi import APIRouter

class FastAPIEndpointGenerator(EndpointGenerator):

    def __init__(self):
        self.router = APIRouter()

    def generate_command_route(self, command: Command, func: CommandFunctionType):
        route_path = f"/{command.__name__.lower()}"
        @self.router.post(route_path, response_model=dict)
        async def dynamic_route(payload: dict):
            parsed_command = command.model_validate(payload)
            func(parsed_command)
            return {}

    def generate_query_route(self, query: Query, func: QueryFunctionType):
        return
        route_path = f"/{query.__name__.lower()}"
        @self.router.get(route_path, response_model=query.__class__)
        async def dynamic_route():
            return func()

    def get_app(self):
        return self.router
