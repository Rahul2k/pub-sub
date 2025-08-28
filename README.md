# In-Memory Pub/Sub System

This project is a high-performance, in-memory Publish/Subscribe system built in Python. It uses the **FastAPI** framework to provide a WebSocket endpoint for real-time messaging and a set of REST APIs for system management and observability.

## Features

* **WebSocket API (`/ws`)**: Real-time `publish`, `subscribe`, `unsubscribe`, and `ping` operations using `asyncio`.
* **REST API**: For topic management (`create`, `delete`, `list`) and observability (`health`, `stats`).
* **Interactive API Docs**: Auto-generated, interactive documentation available at `/docs` via OpenAPI.
* **Graceful Shutdown**: Graceful shutdown handling to cleanly terminate connections.
* **High Concurrency**: Built on `asyncio` to efficiently handle thousands of concurrent connections on a single thread.
* **Message History**: Can replay the last `N` messages to new subscribers on a per-topic basis.
* **Containerized**: Includes a multi-stage `Dockerfile` and a `docker-compose.yml` for easy, one-command deployment.

## How to Run with Docker

This is the easiest and most reliable way to run the service.

### Prerequisites

* Docker
* Docker Compose

### Instructions

1.  **Clone the Repository**:
    Get the project files on your local machine.

2.  **Build and Run the Service**:
    Navigate to the project's root directory and run the following command:
    ```bash
    docker-compose up --build
    ```
    * To run in the background, add the `-d` flag: `docker-compose up --build -d`.

3.  **Access the Service**:
    * **HTTP API**: `http://localhost:8000`
    * **WebSocket API**: `ws://localhost:8000/ws`
    * **Interactive Docs**: `http://localhost:8000/docs`

4.  **View Logs**:
    To view the structured JSON logs from the running container:
    ```bash
    docker-compose logs -f pubsub
    ```

5.  **Stop the Service**:
    To stop the container gracefully, press `Ctrl+C`, or if running in the background, use:
    ```bash
    docker-compose down
    ```
    
## Project Structure
```tree
.
└── pub-sub
    ├── app
    │   ├── __init__.py
    │   ├── config.py
    │   ├── main.py
    │   ├── models.py
    │   └── pubsub.py
    ├── docker-compose.yml
    ├── Dockerfile
    ├── README.md
    └── requirements.txt
```

## Assumptions and Design Choices

This system was built with several key design principles and assumptions in mind 

### Framework
* **FastAPI & Pydantic**: Chosen for its high performance, native `asyncio` support, and excellent developer experience. Pydantic provides robust data validation and serialization at the edge of the API, preventing malformed data from entering the system. The automatic generation of interactive OpenAPI documentation (`/docs`) is a major benefit for API discovery and testing.

### Concurrency Model
* **Asyncio Event Loop**: The application runs on a single thread, using an `asyncio` event loop to manage thousands of concurrent I/O-bound operations (like WebSocket connections) efficiently. This avoids the complexity and overhead of multi-threading.
* **`asyncio.Lock` for Safety**: While single-threaded, race conditions can still occur at `await` points where a task yields control. To ensure data integrity, critical sections that modify shared state (e.g., a topic's subscriber list or message history) are protected by an `asyncio.Lock`.

### Backpressure Policy
* **Policy: Overflow → Disconnect Slow Consumer**: A pub/sub system must be resilient to slow consumers who cannot process messages as fast as they are being produced. This implementation handles backpressure by relying on the OS-level socket buffers and the WebSocket library.
* **Mechanism**: When publishing, messages are sent to all subscribers concurrently via `asyncio.gather`. If a client is slow, its socket buffer will fill up, causing the `websocket.send_json()` call to fail with an exception. This exception is caught, and the slow consumer is immediately removed from the topic's subscriber list and disconnected. This strict but effective policy ensures that one slow client cannot degrade the performance of the entire system for other healthy clients.

### Message History
* **`collections.deque`**: Each topic maintains its own message history using a `collections.deque` with a `maxlen`. This is a highly memory-efficient data structure in Python for implementing a fixed-size circular buffer. When the buffer is full, the oldest message is automatically discarded.

### State Management
* **Ephemeral & In-Memory**: All system state (topics, subscriptions, message history) is stored in Python data structures within the application's memory. No data is persisted to disk. A service restart will result in a clean slate, which aligns with the project requirements.

### Graceful Shutdown
* **FastAPI `lifespan` Manager**: The system handles `SIGINT` (Ctrl+C) and `SIGTERM` (from `docker stop`) signals gracefully.
* **Mechanism**: Upon receiving a shutdown signal, the `lifespan` manager iterates through all active WebSocket connections and sends a standard WebSocket close frame (`code=1001`, reason: "Server is shutting down") to each client. This best-effort approach allows connected clients to detect the shutdown and handle disconnection cleanly on their end.

### Topic Management
* **Explicit Creation**: It is a design assumption that topics must be explicitly created via the `POST /topics` REST endpoint before clients can subscribe or publish to them. This prevents the spontaneous creation of topics from typos and provides a clear administrative control plane.

## API Usage and Testing

For full details, please refer to the interactive documentation at **`http://localhost:8000/docs`**.

### WebSocket Test Cases (Minified JSON)

Use a tool like `websocat` to interact with the WebSocket endpoint.
**Connect command:** `websocat - ws://localhost:8000/ws`
Then, paste any of the single-line messages below and press Enter.

* **Subscribe to a Topic:**
    ```json
    {"type":"subscribe","topic":"orders","client_id":"client-A","request_id":"sub-orders-1"}
    ```
* **Publish a Message:**
    ```json
    {"type":"publish","topic":"orders","request_id":"pub-orders-1","message":{"id":"a7a578a4-a4c3-4318-a6e5-55a2854955b3","payload":{"item":"Wireless Mouse","price":49.99}}}
    ```
* **Ping the Server:**
    ```json
    {"type":"ping","request_id":"ping-1"}
    ```
* **Unsubscribe from a Topic:**
    ```json
    {"type":"unsubscribe","topic":"orders","client_id":"client-A","request_id":"unsub-orders-1"}
    ```
* **Subscribe with History (`last_n`):**
    ```json
    {"type":"subscribe","topic":"orders","client_id":"client-C","last_n":10,"request_id":"sub-history-1"}
    ```
* **Subscribe to Non-Existent Topic (Error Case):**
    ```json
    {"type":"subscribe","topic":"non-existent-topic","client_id":"client-D","request_id":"err-sub-1"}
    ```

## Configuration

The application is configured via environment variables, which can be set in the `docker-compose.yml` file.

* `LOG_LEVEL`: The logging level (e.g., `DEBUG`, `INFO`, `WARNING`). Default: `INFO`.
* `MAX_HISTORY_PER_TOPIC`: The number of messages to store in each topic's history buffer. Default: `50`.


