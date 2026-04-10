import inject
from dw_core.cqrs import Event
from dw_events.adapters import AbstractDeferredEmitter
from dw_events.ports import EventSubscriber
from fastapi import BackgroundTasks


class FastAPIDeferredEmitter(AbstractDeferredEmitter):
    @inject.autoparams('subscriber')
    def __init__(
        self, background_tasks: BackgroundTasks, subscriber: EventSubscriber
    ):
        super().__init__(subscriber)
        self.background_tasks = background_tasks

    def defer_execution(self, event: Event, subscribers):
        for subscriber in subscribers:
            self.background_tasks.add_task(subscriber, event)
