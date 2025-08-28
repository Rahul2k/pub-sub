# in-memory-pubsub-python-prod/app/models.py
from pydantic import BaseModel, Field
from typing import Optional, Any, List, Dict
from datetime import datetime, timezone
import uuid

def get_utc_timestamp() -> str:
    """Returns the current UTC time in ISO 8601 format with a 'Z' suffix."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

class Message(BaseModel):
    id: uuid.UUID
    payload: Any

class ClientMessage(BaseModel):
    type: str
    topic: Optional[str] = None
    message: Optional[Message] = None
    client_id: Optional[str] = None
    last_n: int = 0
    request_id: Optional[str] = None

class ErrorPayload(BaseModel):
    code: str
    message: str

class ServerMessage(BaseModel):
    type: str
    request_id: Optional[str] = Field(default=None)
    topic: Optional[str] = Field(default=None)
    message: Optional[Message] = Field(default=None)
    error: Optional[ErrorPayload] = Field(default=None)
    status: Optional[str] = Field(default=None)
    msg: Optional[str] = Field(default=None)
    ts: str = Field(default_factory=get_utc_timestamp)

# --- Topic Management Models ---
class TopicCreateRequest(BaseModel):
    name: str

class TopicInfo(BaseModel):
    name: str
    subscribers: int

class TopicsListResponse(BaseModel):
    topics: List[TopicInfo]

class HealthResponse(BaseModel):
    status: str = "ok"
    uptime_sec: float
    topics: int
    subscribers: int # This will be total active connections

class TopicStats(BaseModel):
    messages: int
    subscribers: int

class StatsResponse(BaseModel):
    topics: Dict[str, TopicStats]