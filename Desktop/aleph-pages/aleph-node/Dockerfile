FROM python:3.12-slim

LABEL org.opencontainers.image.title="ALEPH Protocol Node"
LABEL org.opencontainers.image.description="Autonomous Agent Knowledge Network — one-command node deployment"
LABEL org.opencontainers.image.source="https://github.com/NovasPlace/aleph-protocol"
LABEL org.opencontainers.image.version="0.1.0"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY node.py .

# Data directory — mount a volume here for persistence
RUN mkdir -p /data
VOLUME /data

ENV ALEPH_DATA_DIR=/data
ENV ALEPH_PORT=8765

EXPOSE 8765

# ALEPH_OPERATOR is required — the container will refuse to start without it.
# Set it when running:  docker run -e ALEPH_OPERATOR="yourname" aleph-node

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8765/health')" || exit 1

CMD ["python", "node.py"]
