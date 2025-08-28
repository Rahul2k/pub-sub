FROM python:3.11-slim as builder

WORKDIR /app
RUN addgroup --system app && adduser --system --group app
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.11-slim

WORKDIR /app
RUN addgroup --system app && adduser --system --group app
COPY --from=builder /opt/venv /opt/venv
COPY ./app ./app
ENV PATH="/opt/venv/bin:$PATH"
RUN chown -R app:app /app
USER app
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--ws-ping-interval", "20", "--ws-ping-timeout", "20"]