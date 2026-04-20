#!/bin/bash
# Gmail MCP Server Kubernetes Installation Script
# Usage: ./k8s/install.sh [--create-namespace]

set -e

NAMESPACE="${NAMESPACE:-llmmllab-mcp}"
REGISTRY=${REGISTRY:-192.168.0.71:31500}
TAG=${TAG:-latest}
CREATE_NAMESPACE="$1"

docker buildx build --platform linux/amd64,linux/arm64 -t ${REGISTRY}/mcp-server-gmail:${TAG} --push .

echo "=== Gmail MCP Server Installation ==="
echo "Namespace: $NAMESPACE"

# Create namespace if requested
if [ "$CREATE_NAMESPACE" = "--create-namespace" ]; then
    echo "Creating namespace $NAMESPACE..."
    kubectl create namespace $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -
fi

# Check for credentials file
if [ ! -f .secrets/credentials.json ]; then
    echo "ERROR: .secrets/credentials.json not found!"
    echo ""
    echo "To set up Gmail OAuth credentials:"
    echo "1. Download your OAuth credentials from Google Cloud Console"
    echo "2. Save as: .secrets/credentials.json"
    echo ""
    exit 1
fi

# Create secrets from local files (pattern from k3s-cluster)
echo "Creating Gmail secrets from local files..."
kubectl create secret generic gmail-secrets \
-n "$NAMESPACE" \
--from-file=credentials.json=.secrets/credentials.json \
--dry-run=client -o yaml | kubectl apply -f -

# Create OAuth JWT signing key secret (generate if not already present)
if ! kubectl get secret gmail-mcp-oauth -n "$NAMESPACE" >/dev/null 2>&1; then
    echo "Generating OAuth JWT signing key..."
    JWT_KEY=$(openssl rand -hex 32)
    kubectl create secret generic gmail-mcp-oauth \
    -n "$NAMESPACE" \
    --from-literal=jwt-signing-key="$JWT_KEY"
else
    echo "OAuth JWT signing key secret already exists, skipping."
fi

# Apply PVCs and deployment
echo "Applying Gmail MCP Server deployment..."
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/referencegrant.yaml

echo ""
echo "=== Installation Complete ==="
echo ""
echo "IMPORTANT: Build and push the Docker image before pods can start:"
echo ""
echo "Then check pod status:"
echo "  kubectl get pods -n $NAMESPACE -l app=mcp-server-gmail"
echo ""
echo "View logs (for OAuth setup):"
echo "  kubectl logs -n $NAMESPACE -l app=mcp-server-gmail -f"
