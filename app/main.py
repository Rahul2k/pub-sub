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

# --- App Lifecycle ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    pubsub = PubSubManager()
    app.state.pubsub = pubsub
    app.state.start_time = time.time()
    logger.info("Pub/Sub server starting up...")
    yield
    logger.info("Pub/Sub server shutting down...")
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