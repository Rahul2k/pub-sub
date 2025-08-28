# app/main.py
import asyncio
import logging
import time
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.routes import service_api, ws_api
from app.pubsub import PubSubManager
from app.config import settings
from app.models import ServerMessage

# --- Log Formatter ---
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


# --- Heartbeat Task ---
async def heartbeat_task(pubsub: PubSubManager):
    """
    A background task that sends a ping to all connected clients every 30 seconds.
    """
    while True:
        await asyncio.sleep(30)
        try:
            # Prepare the ping message once
            ping_message = ServerMessage(type="info", msg="ping")
            json_payload = ping_message.model_dump(mode='json', exclude_none=True)

            # Get a snapshot of current connections
            active_connections = list(pubsub.active_connections.keys())
            if not active_connections:
                continue

            logger.info(f"Sending application heartbeat to {len(active_connections)} clients.")
            
            # Send ping to all clients concurrently
            tasks = [ws.send_json(json_payload) for ws in active_connections]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Log any errors for clients that might have disconnected during the send
            for result in results:
                if isinstance(result, Exception):
                    # These errors are expected if a client disconnects, so we log at a debug level
                    logger.debug(f"Heartbeat send failed for a client: {result}")

        except Exception as e:
            logger.error(f"An error occurred in the heartbeat task: {e}", exc_info=True)


# --- App Lifecycle ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    pubsub = PubSubManager()
    app.state.pubsub = pubsub
    app.state.start_time = time.time()
    
    # Start the background heartbeat task
    heartbeat = asyncio.create_task(heartbeat_task(pubsub))
    app.state.heartbeat_task = heartbeat
    
    logger.info("Pub/Sub server starting up...")
    yield

    # Graceful shutdown - close all active connections and heartbeat task
    logger.info("Pub/Sub server shutting down gracefully ...")

    # Cancel background heartbeat task
    app.state.heartbeat_task.cancel()
    try:
        await app.state.heartbeat_task
    except asyncio.CancelledError:
        logger.info("Heartbeat task successfully cancelled.")
    
    active_connections = list(pubsub.active_connections.keys())
    if active_connections:
        logger.info(f"Closing {len(active_connections)} active WebSocket connections...")
        tasks = [
            ws.close(code=1001, reason="Server is shutting down") 
            for ws in active_connections
        ]
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("All active connections closed.")

app = FastAPI(lifespan=lifespan, title=settings.APP_NAME)

app.include_router(ws_api.router)
app.include_router(service_api.router)