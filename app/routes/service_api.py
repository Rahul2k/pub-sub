import time
from fastapi import APIRouter, Request, status, Path, HTTPException
from fastapi.responses import JSONResponse

from app.models import (
    TopicCreateRequest, TopicsListResponse, TopicInfo, HealthResponse, StatsResponse
)
from app.pubsub import PubSubManager

router = APIRouter(
    tags=["REST API"]
)

@router.post("/topics", status_code=status.HTTP_201_CREATED)
async def create_topic_endpoint(req: TopicCreateRequest, request: Request):
    pubsub: PubSubManager = request.app.state.pubsub
    success = await pubsub.create_topic(req.name)
    if not success:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Topic already exists")
    return {"status": "created", "topic": req.name}

@router.delete("/topics/{name}", status_code=status.HTTP_200_OK)
async def delete_topic_endpoint(request: Request, name: str = Path(..., description="The name of the topic to delete")):
    pubsub: PubSubManager = request.app.state.pubsub
    success = await pubsub.delete_topic(name)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
    return {"status": "deleted", "topic": name}

@router.get("/topics", response_model=TopicsListResponse)
async def list_topics_endpoint(request: Request):
    pubsub: PubSubManager = request.app.state.pubsub
    topic_infos = [
        TopicInfo(name=topic.name, subscribers=len(topic.subscribers))
        for topic in pubsub.topics.values()
    ]
    return TopicsListResponse(topics=topic_infos)

@router.get("/health", response_model=HealthResponse)
async def health_endpoint(request: Request):
    pubsub: PubSubManager = request.app.state.pubsub
    uptime = time.time() - request.app.state.start_time
    return HealthResponse(
        status="ok",
        uptime_sec=uptime,
        topics=len(pubsub.topics),
        subscribers=len(pubsub.active_connections)
    )

@router.get("/stats", response_model=StatsResponse)
async def stats_endpoint(request: Request):
    pubsub: PubSubManager = request.app.state.pubsub
    topic_stats = {
        name: {"messages": len(topic.history), "subscribers": len(topic.subscribers)}
        for name, topic in pubsub.topics.items()
    }
    return JSONResponse(content={"topics": topic_stats})