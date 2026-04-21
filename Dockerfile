# Gmail MCP Server - Docker image for Kubernetes deployment
# Build: docker build -t ${REGISTRY:-localhost:31500}/gmail-mcp-server:${TAG:-latest} .

FROM python:3.12-slim

LABEL maintainer="Scott Long <scott@llmmllab.com>"
LABEL description="Gmail MCP Server"
LABEL version="1.0.0"

# Prevent interactive prompts during build
ENV DEBIAN_FRONTEND=noninteractive

# Set working directory
WORKDIR /app

# Install curl, uv (Python environment manager), and kubectl
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && \
    curl -LsSf https://astral.sh/uv/install.sh | sh && \
    mv /root/.local/bin/uv /usr/local/bin/uv && \
    # Install kubectl
    curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" && \
    chmod +x kubectl && mv kubectl /usr/local/bin/kubectl && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy application code
COPY . .
COPY .secrets/ .secrets/

# Install dependencies (as root, since uv is now in /usr/local/bin)
RUN uv pip install --system .

# Create non-root user and set ownership
RUN useradd -m -s /bin/bash mcp && \
    chown -R mcp:mcp /app

# Switch to non-root user after ownership is set
USER mcp

# Expose port for streaming HTTP transport
EXPOSE 8000

# Default command - use `uv run` to resolve the project venv, then
# `python server.py` so __name__=="__main__" triggers mcp.run() which
# mounts the full OAuth middleware + discovery routes.
CMD ["uv", "run", "python", "server.py"]
