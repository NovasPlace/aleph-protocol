# ALEPH Edge Node Dockerfile
FROM python:3.12-alpine

# Use an unprivileged user for execution
RUN addgroup -S aleph && adduser -S aleph -G aleph

# Set working directory
WORKDIR /home/aleph

# Install dependencies (only SQLite and base network tooling)
RUN apk add --no-cache sqlite bash

# Copy backend requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY node.py .

# Ensure data dictionary permissions
RUN mkdir -p /home/aleph/data && chown -R aleph:aleph /home/aleph

USER aleph

# Run Uvicorn backend over port 8801
CMD ["uvicorn", "node:app", "--host", "0.0.0.0", "--port", "8801"]
