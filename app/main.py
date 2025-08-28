# in-memory-pubsub-python-prod/app/main.py
import logging
import time
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, status, Path, HTTPException
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.models import (
    ClientMessage, ServerMessage, ErrorPayload, TopicCreateRequest,
    TopicsListResponse, TopicInfo, HealthResponse, StatsResponse
)
from app.pubsub import PubSubManager
from app.config import settings

# --- Structured Logging Setup ---
class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "message": record.getMessage(),
            "name": record.name,
        }
        if record.exc_info:
            log_record['exc_info'] = self.formatException(record.exc_info)
        return str(log_record).replace("'", '"')

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter())
logging.basicConfig(level=settings.LOG_LEVEL, handlers=[handler])
logger = logging.getLogger(__name__)

# --- Application Lifecycle ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Application startup
    pubsub = PubSubManager()
    app.state.pubsub = pubsub
    app.state.start_time = time.time()
    logger.info("Pub/Sub server starting up...")
    yield
    # Application shutdown
    logger.info("Pub/Sub server shutting down...")
    
    # --- GRACEFUL SHUTDOWN LOGIC ---
    # Get all active connections
    active_connections = list(pubsub.active_connections.keys())
    if active_connections:
        logger.info(f"Closing {len(active_connections)} active WebSocket connections...")
        # Create a closing task for each connection
        tasks = [
            ws.close(code=1001, reason="Server is shutting down") 
            for ws in active_connections
        ]
        # Run all closing tasks concurrently
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("All active connections closed.")


app = FastAPI(lifespan=lifespan, title=settings.APP_NAME)

# --- WebSocket Endpoint ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    pubsub: PubSubManager = app.state.pubsub
    await websocket.accept()
    await pubsub.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            try:
                msg = ClientMessage.model_validate(data)
                await handle_ws_message(msg, websocket, pubsub)
            except ValidationError as e:
                error_payload = ErrorPayload(code="BAD_REQUEST", message=str(e))
                # FIX: Use model_dump(mode='json')
                await websocket.send_json(ServerMessage(type="error", error=error_payload).model_dump(mode='json', exclude_none=True))
            except WebSocketDisconnect:
                # Re-raise WebSocketDisconnect to be caught by the outer block
                raise
            except Exception as e:
                logger.error(f"Error processing message: {e}", exc_info=True)
                error_payload = ErrorPayload(code="INTERNAL_ERROR", message="An internal error occurred")
                # FIX: Use model_dump(mode='json')
                await websocket.send_json(ServerMessage(type="error", error=error_payload).model_dump(mode='json', exclude_none=True))

    except WebSocketDisconnect:
        logger.info("Client disconnected")
    finally:
        await pubsub.disconnect(websocket)

async def handle_ws_message(msg: ClientMessage, websocket: WebSocket, pubsub: PubSubManager):
    """Main router for incoming WebSocket messages."""
    if msg.type == "ping":
        # FIX: Use model_dump(mode='json')
        await websocket.send_json(ServerMessage(type="pong", request_id=msg.request_id).model_dump(mode='json', exclude_none=True))
        return
        
    if not msg.topic:
        error = ErrorPayload(code="BAD_REQUEST", message="'topic' field is required")
        # FIX: Use model_dump(mode='json')
        await websocket.send_json(ServerMessage(type="error", error=error).model_dump(mode='json', exclude_none=True))
        return
    
    topic = await pubsub.get_topic(msg.topic)
    if not topic:
        error = ErrorPayload(code="TOPIC_NOT_FOUND", message=f"Topic '{msg.topic}' does not exist")
        # FIX: Use model_dump(mode='json')
        await websocket.send_json(ServerMessage(type="error", error=error, request_id=msg.request_id).model_dump(mode='json', exclude_none=True))
        return

    if msg.type == "subscribe":
        await topic.add_subscriber(websocket)
        pubsub.active_connections[websocket].add(msg.topic)
        logger.info(f"Client {msg.client_id or 'N/A'} subscribed to {msg.topic}")
        # FIX: Use model_dump(mode='json')
        await websocket.send_json(ServerMessage(type="ack", status="ok", topic=msg.topic, request_id=msg.request_id).model_dump(mode='json', exclude_none=True))
        
        if msg.last_n > 0:
            history = await topic.get_history(msg.last_n)
            for event in history:
                # FIX: Use model_dump(mode='json')
                await websocket.send_json(event.model_dump(mode='json', exclude_none=True))

    elif msg.type == "unsubscribe":
        await topic.remove_subscriber(websocket)
        pubsub.active_connections[websocket].discard(msg.topic)
        logger.info(f"Client {msg.client_id or 'N/A'} unsubscribed from {msg.topic}")
        # FIX: Use model_dump(mode='json')
        await websocket.send_json(ServerMessage(type="ack", status="ok", topic=msg.topic, request_id=msg.request_id).model_dump(mode='json', exclude_none=True))

    elif msg.type == "publish":
        if not msg.message:
            error = ErrorPayload(code="BAD_REQUEST", message="'message' field is required for publish")
            # FIX: Use model_dump(mode='json')
            await websocket.send_json(ServerMessage(type="error", error=error, request_id=msg.request_id).model_dump(mode='json', exclude_none=True))
            return
        
        await topic.publish(msg.message)
        # FIX: Use model_dump(mode='json')
        await websocket.send_json(ServerMessage(type="ack", status="ok", topic=msg.topic, request_id=msg.request_id).model_dump(mode='json', exclude_none=True))
        
    else:
        error = ErrorPayload(code="BAD_REQUEST", message=f"Unknown message type '{msg.type}'")
        # FIX: Use model_dump(mode='json')
        await websocket.send_json(ServerMessage(type="error", error=error, request_id=msg.request_id).model_dump(mode='json', exclude_none=True))

# --- REST API Endpoints --- (No changes needed below this line)
@app.post("/topics", status_code=status.HTTP_201_CREATED)
async def create_topic_endpoint(req: TopicCreateRequest):
    pubsub: PubSubManager = app.state.pubsub
    success = await pubsub.create_topic(req.name)
    if not success:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Topic already exists")
    return {"status": "created", "topic": req.name}

@app.delete("/topics/{name}", status_code=status.HTTP_200_OK)
async def delete_topic_endpoint(name: str = Path(..., description="The name of the topic to delete")):
    pubsub: PubSubManager = app.state.pubsub
    success = await pubsub.delete_topic(name)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
    return {"status": "deleted", "topic": name}

@app.get("/topics", response_model=TopicsListResponse)
async def list_topics_endpoint():
    pubsub: PubSubManager = app.state.pubsub
    topic_infos = [
        TopicInfo(name=topic.name, subscribers=len(topic.subscribers))
        for topic in pubsub.topics.values()
    ]
    return TopicsListResponse(topics=topic_infos)

@app.get("/health", response_model=HealthResponse)
async def health_endpoint():
    pubsub: PubSubManager = app.state.pubsub
    uptime = time.time() - app.state.start_time
    return HealthResponse(
        status="ok",
        uptime_sec=uptime,
        topics=len(pubsub.topics),
        subscribers=len(pubsub.active_connections)
    )

@app.get("/stats", response_model=StatsResponse)
async def stats_endpoint():
    pubsub: PubSubManager = app.state.pubsub
    topic_stats = {
        name: {"messages": len(topic.history), "subscribers": len(topic.subscribers)}
        for name, topic in pubsub.topics.items()
    }
    return JSONResponse(content={"topics": topic_stats})

{"type":"publish","request_id":"err-bad-req-2","message":{"id":"a6a578a4-a4c3-4318-a6e5-55a2854955b3","payload":"missing topic"}}