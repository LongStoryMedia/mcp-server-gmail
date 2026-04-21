---
name: new-mcp-server
description: Scaffold a new remote FastMCP server — conditional OAuth, HTTP/stdio transport, Pydantic service layer, K8s deployment with RBAC, and multi-arch Docker build. Supports multiple upstream auth types (OAuth 2.0, API key, service account, none). Use when creating a new MCP server from scratch or when asked to bootstrap an MCP server.
---

# New Remote MCP Server Skill

Scaffold a complete, production-ready remote MCP server. The result is a standalone repo directory ready for local dev and Kubernetes deployment.

## What to Build

Produce this directory layout (adapt names to the target service):

```
mcp-server-<name>/
├── server.py          # FastMCP init, tool registration, transport entry point
├── <name>.py          # Service layer: context manager + Pydantic models
├── config.py          # Env-driven config, paths, credential constants
├── oauth_provider.py  # OAuthProxy + JWTVerifier for MCP auth (optional, when MCP_SERVER_BASE_URL set)
├── setup_credentials.py  # One-time credential setup script (if interactive auth flow needed)
├── Dockerfile         # python:3.12-slim + uv, non-root user, port 8000
├── Makefile           # install / start / start-http / build / push / deploy / logs
├── pyproject.toml     # fastmcp>=3.2.4 + service SDK deps, Python >=3.12
├── pyrightconfig.json # basic type checking, python 3.12
└── k8s/
    ├── deployment.yaml  # Deployment + Service + PVCs + ServiceAccount + RBAC
    └── install.sh       # Secret creation + kubectl apply automation
```

## Upstream Auth vs MCP Auth

These are **two separate concerns** — don't conflate them:

1. **Upstream auth** — how the MCP server authenticates with the external service it wraps (e.g., API key for Stripe, OAuth 2.0 token for Google, service account for GCP). This lives in the service layer (`<name>.py`) and `config.py`.

2. **MCP auth** — how MCP clients authenticate with *this* server. This is the `oauth_provider.py` layer, activated by setting `MCP_SERVER_BASE_URL`. Uses Dex as the OIDC provider. Completely independent of upstream auth.

A server can have upstream auth without MCP auth (e.g., local stdio mode with an API key), MCP auth without upstream auth (e.g., wrapping a public API), both, or neither.

## Step-by-Step Instructions

### 1. Gather Requirements First

Ask the user (or infer from context) before writing any code:
- **Service name**: what external API does this server wrap? (e.g., "slack", "stripe", "linear", "k8s")
- **Upstream auth type**: How does the service authenticate? One of:
  - `oauth2` — OAuth 2.0 flow (needs client credentials, token refresh)
  - `api_key` — static API key or token (e.g., Stripe, OpenAI)
  - `service_account` — service account JSON/key file (e.g., GCP, Firebase)
  - `none` — public API or no auth required
- **Tools needed**: What operations should be exposed as MCP tools? (list each with input/output)
- **Credentials**: What secrets need to be stored? Depends on auth type:
  - `oauth2`: client credentials file + refresh token
  - `api_key`: API key string
  - `service_account`: service account JSON file
  - `none`: nothing
- **MCP auth**: Should MCP clients authenticate? (default: yes when deployed to k8s, no for local dev)
- **K8s namespace**: Deploy into which namespace? (default: `llmmllab`)
- **Registry**: Private registry URL (default: `192.168.0.71:31500`)
- **Base URL**: Public HTTPS URL for the MCP server (e.g., `https://mcp.longstorymedia.com`)

### 2. `config.py` — Environment-Driven Configuration

Adapt this template based on the upstream auth type:

```python
import os
from pathlib import Path

SERVICE_NAME = "<name>"

# Paths
SERVICE_DIR = Path(os.environ.get("SERVICE_DIR", f"~/.{SERVICE_NAME}")).expanduser()
SERVICE_DIR.mkdir(parents=True, exist_ok=True)

# --- Upstream credential storage ---
# Choose ONE block based on upstream auth type, delete the rest.

# Option A: OAuth 2.0 upstream (needs client creds + token refresh)
CREDENTIALS_FILE = Path(os.environ.get("CREDENTIALS_FILE", ".secrets/credentials.json"))
TOKEN_FILE = SERVICE_DIR / "token.json"
SCOPES = [
    # add service-specific OAuth scopes here
]

# Option B: API key upstream
API_KEY = os.environ.get(f"{SERVICE_NAME.upper()}_API_KEY", "")

# Option C: Service account upstream (JSON key file)
SERVICE_ACCOUNT_FILE = Path(os.environ.get("SERVICE_ACCOUNT_FILE", ".secrets/service-account.json"))

# Option D: No upstream auth — delete this section entirely

# --- K8s credential persistence (for OAuth 2.0 or any token that needs refresh) ---
# Only needed for auth types that persist tokens. Skip for static API keys.
TOKEN_SOURCE = os.environ.get("TOKEN_SOURCE", "file")  # "file" | "k8s"
K8S_TOKEN_SECRET_NAME = os.environ.get("K8S_TOKEN_SECRET_NAME", f"{SERVICE_NAME}-secrets")
K8S_TOKEN_SECRET_KEY = os.environ.get("K8S_TOKEN_SECRET_KEY", "token.json")
K8S_TOKEN_MOUNT_PATH = Path(os.environ.get("K8S_TOKEN_MOUNT_PATH", f"/var/run/{SERVICE_NAME}-token"))

# --- MCP transport & auth ---
MCP_TRANSPORT = os.environ.get("MCP_TRANSPORT", "http")  # "http" | "stdio"
MCP_SERVER_BASE_URL = os.environ.get("MCP_SERVER_BASE_URL")  # None = no MCP auth

# Dex OIDC (only used when MCP_SERVER_BASE_URL is set — this is MCP client auth, not upstream auth)
DEX_ISSUER = os.environ.get("DEX_ISSUER", "https://auth.longstorymedia.com")
DEX_INTERNAL_URL = os.environ.get("DEX_INTERNAL_URL", "http://dex.auth.svc.cluster.local:5556")
OAUTH_CLIENT_ID = os.environ.get("OAUTH_CLIENT_ID", f"{SERVICE_NAME}-mcp-client")
OAUTH_JWT_SIGNING_KEY = os.environ.get("OAUTH_JWT_SIGNING_KEY", "")
```

### 3. `oauth_provider.py` — MCP Client Auth (Dex Integration)

This file handles **MCP client authentication** — how clients prove identity to *this* server. It is completely independent of how the server authenticates with its upstream service.

Only needed when `MCP_SERVER_BASE_URL` is set. Copy this pattern verbatim:

```python
from fastmcp.server.auth import OAuthProxy
from fastmcp.server.auth.providers.jwt import JWTVerifier
from config import DEX_ISSUER, DEX_INTERNAL_URL, OAUTH_CLIENT_ID, OAUTH_JWT_SIGNING_KEY

def create_oauth_provider() -> OAuthProxy:
    # Split URLs: browser → public Dex, server-to-server → internal k8s DNS
    token_verifier = JWTVerifier(
        jwks_uri=f"{DEX_INTERNAL_URL}/keys",
        issuer=DEX_ISSUER,
        audience=OAUTH_CLIENT_ID,
        # Do NOT set required_scopes: Dex ID tokens lack scope claim
    )

    return OAuthProxy(
        upstream_authorization_endpoint=f"{DEX_ISSUER}/auth",
        upstream_token_endpoint=f"{DEX_INTERNAL_URL}/token",
        upstream_client_id=OAUTH_CLIENT_ID,
        token_endpoint_auth_method="none",   # public client
        token_verifier=token_verifier,
        jwt_signing_key=OAUTH_JWT_SIGNING_KEY,
        allowed_redirect_uris=["http://localhost:*", "http://127.0.0.1:*"],
        extra_authorize_params={"scope": "openid"},
    )
```

**Key invariants** — never break these:
- `token_endpoint_auth_method="none"` — Dex configured as `public: true`
- `jwks_uri` and `upstream_token_endpoint` use internal k8s DNS (avoids external round-trips)
- `upstream_authorization_endpoint` uses public URL (browser must reach it)
- No `required_scopes` on `JWTVerifier` — Dex ID tokens don't include the scope claim

### 4. `<name>.py` — Service Layer

Use a context manager + Pydantic pattern. Adapt credential loading to the upstream auth type:

#### OAuth 2.0 upstream (token refresh flow)

```python
from contextlib import contextmanager
from pydantic import BaseModel
from config import TOKEN_FILE, CREDENTIALS_FILE, SCOPES, TOKEN_SOURCE, K8S_TOKEN_MOUNT_PATH, K8S_TOKEN_SECRET_KEY

class SomeResource(BaseModel):
    id: str
    name: str
    field: str | None = None

def get_credentials():
    """Load + refresh OAuth 2.0 credentials from file or K8s secret."""
    use_k8s = TOKEN_SOURCE == "k8s"
    token_path = K8S_TOKEN_MOUNT_PATH / K8S_TOKEN_SECRET_KEY if use_k8s else TOKEN_FILE
    # ... load token, check expiry, refresh if needed, save back
    return creds

class ServiceClient:
    def __enter__(self):
        self.creds = get_credentials()
        self.client = build_client(self.creds)  # e.g., httpx.Client with Bearer token
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def list_resources(self, query: str) -> list[SomeResource]:
        raw = self.client.get("/resources", params={"q": query}).json()
        return [SomeResource.model_validate(item) for item in raw["items"]]
```

#### API key upstream

```python
from pydantic import BaseModel
from config import API_KEY

class SomeResource(BaseModel):
    id: str
    name: str

class ServiceClient:
    def __enter__(self):
        import httpx
        self.client = httpx.Client(
            base_url="https://api.example.com/v1",
            headers={"Authorization": f"Bearer {API_KEY}"},
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.client.close()

    def list_resources(self, query: str) -> list[SomeResource]:
        raw = self.client.get("/resources", params={"q": query}).json()
        return [SomeResource.model_validate(item) for item in raw["items"]]
```

#### Service account upstream

```python
from pydantic import BaseModel
from config import SERVICE_ACCOUNT_FILE

class SomeResource(BaseModel):
    id: str
    name: str

class ServiceClient:
    def __enter__(self):
        # Load service account JSON, build authenticated client
        # e.g., google.oauth2.service_account.Credentials.from_service_account_file(...)
        self.client = build_client_from_service_account(SERVICE_ACCOUNT_FILE)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def list_resources(self, query: str) -> list[SomeResource]:
        raw = self.client.get("/resources", params={"q": query}).json()
        return [SomeResource.model_validate(item) for item in raw["items"]]
```

#### No upstream auth

```python
from pydantic import BaseModel

class SomeResource(BaseModel):
    id: str
    name: str

class ServiceClient:
    def __enter__(self):
        import httpx
        self.client = httpx.Client(base_url="https://api.example.com/v1")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.client.close()

    def list_resources(self, query: str) -> list[SomeResource]:
        raw = self.client.get("/resources", params={"q": query}).json()
        return [SomeResource.model_validate(item) for item in raw["items"]]
```

**Rules for the service layer (all auth types):**
- Every method returns typed Pydantic models, not raw dicts
- For OAuth 2.0: credentials loaded fresh per context entry (auto-refresh handled inside `get_credentials`)
- For OAuth 2.0 in K8s: try writing refreshed token to mount path first, fall back to `kubectl patch secret`
- No global state — context manager only

### 5. `server.py` — Tool Registration

```python
from config import MCP_SERVER_BASE_URL, MCP_TRANSPORT

if MCP_SERVER_BASE_URL:
    from oauth_provider import create_oauth_provider
    mcp = FastMCP("<name>", auth=create_oauth_provider())
else:
    mcp = FastMCP("<name>", auth=None)

from <name> import ServiceClient  # import AFTER mcp init

@mcp.tool(name="list_things", description="List things matching a query.")
def list_things_impl(query: str, max_results: int = 10) -> dict:
    with ServiceClient() as client:
        results = client.list_resources(query)
        return {"count": len(results), "items": [r.model_dump() for r in results]}

if __name__ == "__main__":
    if MCP_TRANSPORT == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="http", host="0.0.0.0", port=8000)
```

**Rules for tools:**
- Each tool creates a fresh `ServiceClient()` context — no shared state
- Return plain dicts (JSON-serializable), not Pydantic objects
- Use `dry_run: bool = True` default for any destructive operations (delete, modify)
- Descriptive `name=` and `description=` on every `@mcp.tool()` decorator

### 6. `Dockerfile`

```dockerfile
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && \
    rm -rf /var/lib/apt/lists/* && \
    curl -LsSf https://astral.sh/uv/install.sh | sh && \
    mv /root/.local/bin/uv /usr/local/bin/uv

# kubectl (only needed if using K8s token persistence)
RUN KUBECTL_VERSION=$(curl -s https://dl.k8s.io/release/stable.txt) && \
    curl -LO "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/$(dpkg --print-architecture)/kubectl" && \
    chmod +x kubectl && mv kubectl /usr/local/bin/kubectl

WORKDIR /app
COPY . .
RUN uv pip install --system .

RUN useradd -m -s /bin/bash mcp && chown -R mcp:mcp /app
USER mcp

EXPOSE 8000
CMD ["uv", "run", "python", "server.py"]
```

### 7. `Makefile`

```makefile
REGISTRY   := 192.168.0.71:31500
IMAGE_NAME := mcp-server-<name>
IMAGE      := $(REGISTRY)/$(IMAGE_NAME):latest
NAMESPACE  := llmmllab

.PHONY: install start start-http build push deploy apply restart logs setup-credentials

install:
	uv sync

start:
	MCP_TRANSPORT=stdio uv run python server.py

start-http:
	MCP_TRANSPORT=http uv run python server.py

build:
	docker buildx build --platform linux/amd64,linux/arm64 -t $(IMAGE) --push .

push: build

deploy: push
	./k8s/install.sh --create-namespace

apply:
	kubectl apply -f k8s/deployment.yaml

restart:
	kubectl rollout restart deployment/$(IMAGE_NAME) -n $(NAMESPACE)

logs:
	kubectl logs -n $(NAMESPACE) -l app=$(IMAGE_NAME) -f

# Only include if upstream auth requires interactive credential setup (OAuth 2.0)
setup-credentials:
	uv run python setup_credentials.py
```

### 8. `k8s/deployment.yaml`

Use this template. Replace `<name>` and adjust env/volumes for the upstream auth type:

- **OAuth 2.0 upstream**: mount token secret volume + set `TOKEN_SOURCE=k8s`
- **API key upstream**: inject key via secretKeyRef env var (no volume needed)
- **Service account upstream**: mount service account JSON as a secret volume
- **No upstream auth**: remove credential-related env/volumes entirely

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mcp-server-<name>
  namespace: llmmllab
spec:
  replicas: 1
  selector:
    matchLabels:
      app: mcp-server-<name>
  template:
    metadata:
      labels:
        app: mcp-server-<name>
    spec:
      serviceAccountName: mcp-server-<name>
      nodeSelector:
        kubernetes.io/arch: arm64
      containers:
        - name: mcp-server-<name>
          image: 192.168.0.71:31500/mcp-server-<name>:latest
          imagePullPolicy: Always
          ports:
            - containerPort: 8000
          env:
            # --- MCP transport & auth (always present) ---
            - name: MCP_TRANSPORT
              value: "http"
            - name: MCP_SERVER_BASE_URL
              value: "https://mcp.longstorymedia.com"
            - name: DEX_ISSUER
              value: "https://auth.longstorymedia.com"
            - name: DEX_INTERNAL_URL
              value: "http://dex.auth.svc.cluster.local:5556"
            - name: OAUTH_CLIENT_ID
              value: "<name>-mcp-client"
            - name: OAUTH_JWT_SIGNING_KEY
              valueFrom:
                secretKeyRef:
                  name: <name>-mcp-oauth
                  key: jwt_signing_key
            - name: POD_NAMESPACE
              valueFrom:
                fieldRef:
                  fieldPath: metadata.namespace
            # --- Upstream auth env vars (choose based on auth type) ---
            # Option A: OAuth 2.0 upstream
            - name: TOKEN_SOURCE
              value: "k8s"
            - name: K8S_TOKEN_MOUNT_PATH
              value: "/var/run/<name>-token"
            # Option B: API key upstream
            # - name: <NAME>_API_KEY
            #   valueFrom:
            #     secretKeyRef:
            #       name: <name>-secrets
            #       key: api_key
            # Option C: Service account upstream
            # - name: SERVICE_ACCOUNT_FILE
            #   value: "/var/run/<name>-credentials/service-account.json"
          readinessProbe:
            tcpSocket:
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 10
          livenessProbe:
            tcpSocket:
              port: 8000
            initialDelaySeconds: 10
            periodSeconds: 30
          resources:
            requests:
              memory: "256Mi"
              cpu: "100m"
            limits:
              memory: "512Mi"
              cpu: "500m"
          volumeMounts:
            # Include only what's needed for the upstream auth type:
            # OAuth 2.0: token secret mount
            - name: <name>-token-secret
              mountPath: /var/run/<name>-token
            # Service account: credentials mount
            # - name: <name>-credentials
            #   mountPath: /var/run/<name>-credentials
            # Persistent storage for jobs/data (optional)
            - name: <name>-jobs
              mountPath: /home/mcp/.<name>-jobs
      volumes:
        # OAuth 2.0: token secret
        - name: <name>-token-secret
          secret:
            secretName: <name>-secrets
        # Service account: credentials secret
        # - name: <name>-credentials
        #   secret:
        #     secretName: <name>-credentials
        # Persistent storage (optional)
        - name: <name>-jobs
          persistentVolumeClaim:
            claimName: <name>-jobs-pvc
---
apiVersion: v1
kind: Service
metadata:
  name: mcp-server-<name>
  namespace: llmmllab
spec:
  selector:
    app: mcp-server-<name>
  ports:
    - protocol: TCP
      port: 8000
      targetPort: 8000
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: <name>-jobs-pvc
  namespace: llmmllab
spec:
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: 10Mi
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: mcp-server-<name>
  namespace: llmmllab
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: mcp-server-<name>
  namespace: llmmllab
rules:
  - apiGroups: [""]
    resources: ["secrets"]
    resourceNames: ["<name>-secrets"]
    verbs: ["get", "patch", "update"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: mcp-server-<name>
  namespace: llmmllab
subjects:
  - kind: ServiceAccount
    name: mcp-server-<name>
    namespace: llmmllab
roleRef:
  kind: Role
  name: mcp-server-<name>
  apiGroup: rbac.authorization.k8s.io
```

### 9. `k8s/install.sh`

Adapt the secret creation block to the upstream auth type:

```bash
#!/usr/bin/env bash
set -euo pipefail

NAMESPACE=${NAMESPACE:-llmmllab}
SERVICE=<name>

if [[ "${1:-}" == "--create-namespace" ]]; then
  kubectl get namespace "$NAMESPACE" &>/dev/null || kubectl create namespace "$NAMESPACE"
fi

# --- Upstream credential secret (choose ONE based on auth type) ---

# Option A: OAuth 2.0 — client credentials JSON + token file
if [[ -f ".secrets/credentials.json" ]]; then
  kubectl create secret generic "${SERVICE}-secrets" \
    --namespace "$NAMESPACE" \
    --from-file=credentials.json=.secrets/credentials.json \
    --dry-run=client -o yaml | kubectl apply -f -
fi

# Option B: API key — single key string
# kubectl create secret generic "${SERVICE}-secrets" \
#   --namespace "$NAMESPACE" \
#   --from-literal=api_key="${API_KEY:?Set API_KEY env var}" \
#   --dry-run=client -o yaml | kubectl apply -f -

# Option C: Service account — JSON key file
# kubectl create secret generic "${SERVICE}-credentials" \
#   --namespace "$NAMESPACE" \
#   --from-file=service-account.json=.secrets/service-account.json \
#   --dry-run=client -o yaml | kubectl apply -f -

# Option D: No upstream auth — skip secret creation

# --- MCP auth JWT signing key (always needed when MCP_SERVER_BASE_URL is set) ---
if ! kubectl get secret "${SERVICE}-mcp-oauth" -n "$NAMESPACE" &>/dev/null; then
  kubectl create secret generic "${SERVICE}-mcp-oauth" \
    --namespace "$NAMESPACE" \
    --from-literal=jwt_signing_key="$(openssl rand -hex 32)"
fi

kubectl apply -f k8s/deployment.yaml
```

### 10. `pyproject.toml`

```toml
[project]
name = "mcp-server-<name>"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastmcp>=3.2.4",
    # add upstream service SDK here based on auth type, e.g.:
    # API key/no auth: "httpx>=0.28.1",
    # OAuth 2.0: "authlib>=1.3.0", "httpx>=0.28.1",
    # GCP service: "google-auth>=2.28.0", "google-api-python-client>=2.194.0",
]
```

## Quality Checklist

Before reporting the scaffold as complete, verify:

- [ ] `config.py` has `MCP_SERVER_BASE_URL` (activates MCP auth) and `MCP_TRANSPORT` env vars
- [ ] `config.py` upstream credential config matches the chosen auth type (no leftover options)
- [ ] `server.py` conditionally imports `oauth_provider` only when `MCP_SERVER_BASE_URL` is set
- [ ] Every tool returns a plain dict, not a Pydantic model
- [ ] Every destructive tool has `dry_run: bool = True` default
- [ ] `oauth_provider.py` uses split URLs (public Dex for browser, internal DNS for server)
- [ ] K8s RBAC only grants access to the specific secret(s) by name
- [ ] Dockerfile uses non-root `mcp` user
- [ ] `install.sh` is idempotent (uses `--dry-run=client | kubectl apply`)
- [ ] Node selector `kubernetes.io/arch: arm64` is present in deployment
- [ ] K8s deployment env/volumes match the chosen upstream auth type (no commented-out options left)
- [ ] `pyproject.toml` includes only the dependencies needed for the chosen auth type

## Common Pitfalls

**Don't:**
- Conflate MCP client auth (`oauth_provider.py`) with upstream service auth (`<name>.py`) — they're independent
- Set `required_scopes` on `JWTVerifier` — Dex ID tokens don't include scope claim
- Use `auth_method="client_secret_post"` — Dex is configured as a public client
- Share service client state across tool calls — always use a fresh context manager
- Use `kubectl apply` without `--dry-run=client` for secret creation (breaks idempotency)
- Hardcode the registry or namespace — use Makefile variables
- Include OAuth 2.0 token persistence config when the upstream uses a static API key
- Include K8s token mount volumes when the upstream doesn't need persistent tokens

**Do:**
- Use `token_endpoint_auth_method="none"` for public Dex clients
- For OAuth 2.0 upstream: always refresh credentials inside `get_credentials()` before returning them
- For API key upstream: load key from env var, not from a file
- Fall back gracefully when `kubectl patch` fails (token write permission issues)
- Test both `stdio` and `http` transports locally before deploying
- Strip unused auth options from config/deployment before delivering — don't leave commented-out alternatives
