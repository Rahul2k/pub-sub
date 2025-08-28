import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.models import ClientMessage, ServerMessage, ErrorPayload
from app.pubsub import PubSubManager

router = APIRouter()
logger = logging.getLogger(__name__)

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    pubsub: PubSubManager = websocket.app.state.pubsub
    
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
                await websocket.send_json(ServerMessage(type="error", error=error_payload).model_dump(mode='json', exclude_none=True))
            except WebSocketDisconnect:
                raise
            except Exception as e:
                logger.error(f"Error processing message: {e}", exc_info=True)
                error_payload = ErrorPayload(code="INTERNAL_ERROR", message="An internal error occurred")
                await websocket.send_json(ServerMessage(type="error", error=error_payload).model_dump(mode='json', exclude_none=True))

    except WebSocketDisconnect:
        logger.info("Client disconnected")
    finally:
        await pubsub.disconnect(websocket)

async def handle_ws_message(msg: ClientMessage, websocket: WebSocket, pubsub: PubSubManager):

    if msg.type == "ping":
        await websocket.send_json(ServerMessage(type="pong", request_id=msg.request_id).model_dump(mode='json', exclude_none=True))
        return
        
    if not msg.topic:
        error = ErrorPayload(code="BAD_REQUEST", message="'topic' field is required")
        await websocket.send_json(ServerMessage(type="error", error=error).model_dump(mode='json', exclude_none=True))
        return
    
    topic = await pubsub.get_topic(msg.topic)
    if not topic:
        error = ErrorPayload(code="TOPIC_NOT_FOUND", message=f"Topic '{msg.topic}' does not exist")
        await websocket.send_json(ServerMessage(type="error", error=error, request_id=msg.request_id).model_dump(mode='json', exclude_none=True))
        return

    if msg.type == "subscribe":
        await topic.add_subscriber(websocket)
        pubsub.active_connections[websocket].add(msg.topic)
        logger.info(f"Client {msg.client_id or 'N/A'} subscribed to {msg.topic}")
        await websocket.send_json(ServerMessage(type="ack", status="ok", topic=msg.topic, request_id=msg.request_id).model_dump(mode='json', exclude_none=True))
        
        if msg.last_n > 0:
            history = await topic.get_history(msg.last_n)
            for event in history:
                await websocket.send_json(event.model_dump(mode='json', exclude_none=True))

    elif msg.type == "unsubscribe":
        await topic.remove_subscriber(websocket)
        pubsub.active_connections[websocket].discard(msg.topic)
        logger.info(f"Client {msg.client_id or 'N/A'} unsubscribed from {msg.topic}")
        await websocket.send_json(ServerMessage(type="ack", status="ok", topic=msg.topic, request_id=msg.request_id).model_dump(mode='json', exclude_none=True))

    elif msg.type == "publish":
        if not msg.message:
            error = ErrorPayload(code="BAD_REQUEST", message="'message' field is required for publish")
            await websocket.send_json(ServerMessage(type="error", error=error, request_id=msg.request_id).model_dump(mode='json', exclude_none=True))
            return
        
        await topic.publish(msg.message)
        await websocket.send_json(ServerMessage(type="ack", status="ok", topic=msg.topic, request_id=msg.request_id).model_dump(mode='json', exclude_none=True))
        
    else:
        error = ErrorPayload(code="BAD_REQUEST", message=f"Unknown message type '{msg.type}'")
        await websocket.send_json(ServerMessage(type="error", error=error, request_id=msg.request_id).model_dump(mode='json', exclude_none=True))