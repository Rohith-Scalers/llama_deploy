import asyncio
from typing import Any, Callable, Dict, List, Optional

from agentfile.services.base import BaseService
from agentfile.control_plane.base import BaseControlPlane
from agentfile.message_consumers.base import BaseMessageQueueConsumer
from agentfile.message_queues.simple import SimpleMessageQueue
from agentfile.messages.base import QueueMessage
from agentfile.types import ActionTypes, TaskDefinition


class HumanMessageConsumer(BaseMessageQueueConsumer):
    message_handler: Dict[str, Callable]
    message_type: str = "human"

    async def _process_message(self, message: QueueMessage, **kwargs: Any) -> None:
        action = message.action
        if action not in self.message_handler:
            raise ValueError(f"Action {action} not supported by control plane")

        if action == ActionTypes.COMPLETED_TASK:
            await self.message_handler[action](result=message.data)


class LocalLauncher:
    def __init__(
        self,
        services: List[BaseService],
        control_plane: BaseControlPlane,
        message_queue: SimpleMessageQueue,
    ) -> None:
        self.services = services
        self.control_plane = control_plane
        self.message_queue = message_queue

    async def handle_human_message(self, **kwargs: Any) -> None:
        print("Got response:\n", str(kwargs), flush=True)
        self.message_queue.running = False

    async def register_consumers(
        self, consumers: Optional[List[BaseMessageQueueConsumer]] = None
    ) -> None:
        for service in self.services:
            await self.message_queue.register_consumer(service.as_consumer())

        consumers = consumers or []
        for consumer in consumers:
            await self.message_queue.register_consumer(consumer)

        await self.message_queue.register_consumer(self.control_plane.as_consumer())

    def launch_single(self, initial_task: str) -> None:
        asyncio.run(self.alaunch_single(initial_task))

    async def alaunch_single(self, initial_task: str) -> None:
        # register human consumer
        human_consumer = HumanMessageConsumer(
            message_handler={
                ActionTypes.COMPLETED_TASK: self.handle_human_message,
            }
        )
        await self.register_consumers([human_consumer])

        # publish initial task
        await self.message_queue.publish(
            QueueMessage(
                type="control_plane",
                action=ActionTypes.NEW_TASK,
                data=TaskDefinition(input=initial_task).dict(),
            )
        )

        # register each service to the control plane
        for service in self.services:
            await self.control_plane.register_service(service.service_definition)

        # start services
        for service in self.services:
            asyncio.create_task(service.launch_local())

        # runs until the message queue is stopped by the human consumer
        await self.message_queue.start()
