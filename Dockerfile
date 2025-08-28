# in-memory-pubsub-python-prod/Dockerfile

# --- Stage 1: Builder ---
# Use a specific Python version for reproducibility
FROM python:3.11-slim as builder

# Set working directory
WORKDIR /app

# Create a non-root user and group
RUN addgroup --system app && adduser --system --group app

# Create a virtual environment to isolate dependencies
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Stage 2: Final Image ---
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Create the same non-root user as in the builder stage
RUN addgroup --system app && adduser --system --group app

# Copy the virtual environment from the builder stage
COPY --from=builder /opt/venv /opt/venv

# Copy application code
COPY ./app ./app

# Set the path to include the virtual environment's binaries
ENV PATH="/opt/venv/bin:$PATH"

# Change ownership of the app directory to the non-root user
RUN chown -R app:app /app

# Switch to the non-root user
USER app

# Expose the port the server runs on
EXPOSE 8000

# Run the application using Uvicorn with production-ready settings
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]