from dw_core.cqrs import Command, Event
from dw_events.ports import DeferredEmitter
from typing import Callable
from unittest import skip


class ApiDeferSpec:
    def given_port(self, port):
        raise NotImplementedError()

    def given_subscription(
        self, event_class: Event, executer: Callable[[Event], None]
    ):
        raise NotImplementedError()

    def given_generated_endpoints(self):
        raise NotImplementedError()

    def when_call(self, instance):
        raise NotImplementedError()

    def assert_execution_deferred(self):
        raise NotImplementedError()

    def assert_task_queue(self):
        raise NotImplementedError()

    def assert_handler_called(self, handler):
        raise NotImplementedError()

    def test_deffer_execution(self):
        class Echo(Command):
            message: str

        class Echoed(Event):
            message: str

        def echo(msg: Echo, deferred_emitter: DeferredEmitter) -> None:
            print(msg.message)
            deferred_emitter.defer_emit(Echoed(message=msg.message))

        self.given_port(echo)
        self.given_generated_endpoints()

        self.when_call(Echo(message='Hello World'))

        self.assert_execution_deferred()

    @skip('TODO')
    def test_task_queue(self):
        class Echo(Command):
            message: str

        class Echoed(Event):
            message: str

        def echo(msg: Echo, deferred_emitter: DeferredEmitter) -> None:
            print(msg.message)
            deferred_emitter.defer_emit(Echoed(message=msg.message))

        self.given_port(echo)
        self.given_generated_endpoints()

        self.when_call(Echo(message='Hello World'))

        self.assert_task_queue()

    def test_event_handler_was_called(self):
        class Echo(Command):
            message: str

        class Echoed(Event):
            message: str

        def echo(msg: Echo, deferred_emitter: DeferredEmitter) -> None:
            deferred_emitter.defer_emit(Echoed(message=msg.message))

        def gossip(echoed: Echoed):
            pass

        self.given_port(echo)
        self.given_subscription(Echoed, gossip)
        self.given_generated_endpoints()

        self.when_call(Echo(message='Hello World'))

        # self.assert_handler_called(gossip)
