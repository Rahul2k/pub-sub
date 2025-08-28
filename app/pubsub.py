# in-memory-pubsub-python-prod/app/pubsub.py
import asyncio
import logging
from collections import deque
from typing import Dict, Set, List
from starlette.websockets import WebSocket

from app.models import Message, ServerMessage
from app.config import settings

logger = logging.getLogger(__name__)

class Topic:
    """Manages a single topic, its subscribers, and message history."""
    def __init__(self, name: str):
        self.name = name
        self.subscribers: Set[WebSocket] = set()
        self.history: deque = deque(maxlen=settings.MAX_HISTORY_PER_TOPIC)
        self._lock = asyncio.Lock()

    async def add_subscriber(self, websocket: WebSocket):
        async with self._lock:
            self.subscribers.add(websocket)

    async def remove_subscriber(self, websocket: WebSocket):
        async with self._lock:
            self.subscribers.discard(websocket)

    async def publish(self, message: Message):
        """Adds a message to history and broadcasts it to subscribers."""
        async with self._lock:
            server_message = ServerMessage(type="event", topic=self.name, message=message)
            self.history.append(server_message)
            
            if not self.subscribers:
                return

            # FIX: Use model_dump(mode='json') to convert UUID to string
            json_payload = server_message.model_dump(mode='json', exclude_none=True)

            tasks = [
                ws.send_json(json_payload)
                for ws in self.subscribers
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for ws, result in zip(list(self.subscribers), results):
                if isinstance(result, Exception):
                    logger.warning(f"Failed to send to subscriber on topic {self.name}: {result}. Removing.")
                    self.subscribers.discard(ws)

    async def get_history(self, n: int) -> List[ServerMessage]:
        async with self._lock:
            if n <= 0 or n > len(self.history):
                return list(self.history)
            return list(self.history)[-n:]

class PubSubManager:
    """The central manager for all topics and WebSocket connections."""
    def __init__(self):
        self.topics: Dict[str, Topic] = {}
        self.active_connections: Dict[WebSocket, Set[str]] = {} # ws -> {topic1, topic2}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        self.active_connections[websocket] = set()

    async def disconnect(self, websocket: WebSocket):
        """Handle client disconnection, unsubscribing from all topics."""
        subscribed_topics = self.active_connections.pop(websocket, set())
        for topic_name in subscribed_topics:
            if topic := self.topics.get(topic_name):
                await topic.remove_subscriber(websocket)
                logger.info(f"Unsubscribed disconnected client from {topic_name}")

    async def create_topic(self, topic_name: str) -> bool:
        """Creates a new topic. Returns False if it already exists."""
        async with self._lock:
            if topic_name in self.topics:
                return False
            self.topics[topic_name] = Topic(topic_name)
            logger.info(f"Topic created: {topic_name}")
            return True

    async def delete_topic(self, topic_name: str) -> bool:
        """Deletes a topic. Returns False if it doesn't exist."""
        async with self._lock:
            if topic_name not in self.topics:
                return False
            
            topic_to_delete = self.topics.pop(topic_name)
            info_message = ServerMessage(
                type="info", topic=topic_name, msg="topic_deleted"
            )
            
            # FIX: Use model_dump(mode='json')
            json_payload = info_message.model_dump(mode='json', exclude_none=True)
            
            tasks = [
                ws.send_json(json_payload)
                for ws in topic_to_delete.subscribers
            ]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

            for ws in topic_to_delete.subscribers:
                if ws_subs := self.active_connections.get(ws):
                    ws_subs.discard(topic_name)
            
            logger.info(f"Topic deleted: {topic_name}")
            return True
    
    async def get_topic(self, topic_name: str) -> Topic | None:
        return self.topics.get(topic_name)