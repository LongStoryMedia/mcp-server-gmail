# Gmail MCP Server

A [FastMCP](https://gofastmcp.com/) server that provides Gmail integration for AI assistants via the Model Context Protocol. Supports OAuth 2.0 authentication through [Dex](https://dexidp.io/) + OpenLDAP and deploys to Kubernetes.

## Features

- **Search & read** emails with full body extraction (HTML and plain text)
- **Grep** email bodies with pattern matching and context lines
- **Count** emails matching a query
- **Delete** emails (with dry-run support)
- **Label management** — create, list, and apply labels to emails
- **OAuth 2.0** authentication via Dex (OIDC/LDAP) using FastMCP's `OAuthProxy`
- **Dual transport** — stdio for local MCP clients, HTTP for networked/k8s use

## Architecture

```
┌──────────────┐       ┌──────────────────┐       ┌─────────────────────┐
│  MCP Client  │──────▶│  Gmail MCP       │──────▶│  Dex (OAuth/OIDC)   │
│  (Claude,    │  MCP  │  Server          │ authz │  + OpenLDAP         │
│   etc.)      │       │  (FastMCP)       │       │  (auth namespace)   │
└──────────────┘       └──────────────────┘       └─────────────────────┘
                               │
                               ▼
                       ┌─────────────────┐
                       │  Gmail API      │
                       │  (Google)       │
                       └─────────────────┘
```

**OAuth flow summary:**  
FastMCP's `OAuthProxy` presents a DCR-compliant interface to MCP clients. The user's browser is redirected to Dex (public issuer URL) for login via LDAP. Token exchange and JWKS verification happen server-to-server over the internal k8s DNS name (`dex.auth.svc.cluster.local:5556`), avoiding external network round-trips.

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- Google Cloud project with Gmail API enabled
- OAuth credentials from Google Cloud Console saved as `.secrets/credentials.json`

### Local Development (no OAuth)

```bash
make install              # Install dependencies
make setup-oauth          # One-time: run Google OAuth flow to get token
make start                # Run with stdio transport
make start-http           # Run with HTTP transport on :8000
```

When `MCP_SERVER_BASE_URL` is **not** set, the server runs without authentication (suitable for local stdio use).

### Local Development (with OAuth)

```bash
MCP_SERVER_BASE_URL=http://localhost:8000 \
DEX_ISSUER=https://auth.longstorymedia.com \
DEX_INTERNAL_URL=http://dex.auth.svc.cluster.local:5556 \
OAUTH_CLIENT_ID=gmail-mcp-client \
OAUTH_JWT_SIGNING_KEY=$(openssl rand -hex 32) \
make start-http
```

### Kubernetes Deployment

```bash
make deploy     # Build multi-arch image, push to registry, create secrets, apply manifests
```

Or step by step:

```bash
make push       # Build and push Docker image
./k8s/install.sh --create-namespace   # Create namespace, secrets, apply manifests
```

The install script will:
1. Build and push a multi-arch Docker image to the private registry
2. Create the `gmail-secrets` secret from `.secrets/credentials.json`
3. Generate an `gmail-mcp-oauth` secret with a random JWT signing key (if it doesn't exist)
4. Apply all k8s manifests (Deployment, Service, PVCs)

## Makefile Targets

```
make help         # Show all targets
```

| Target | Description |
|---|---|
| `install` | Install Python dependencies (`uv sync`) |
| `start` | Run locally with stdio transport |
| `start-http` | Run locally with HTTP transport on port 8000 |
| `test` | Run tests (`pytest`) |
| `validate` | Type-check with `pyright` |
| `build` | Build multi-arch Docker image |
| `push` | Build and push to private registry |
| `deploy` | Full build + push + k8s install |
| `apply` | Apply k8s manifests only (no build) |
| `restart` | Rolling restart of the k8s deployment |
| `logs` | Tail pod logs |
| `status` | Show pod status |
| `describe` | Describe the k8s deployment |
| `setup-oauth` | Run Google OAuth credential setup |
| `clean` | Remove caches and build artifacts |

## Environment Variables

| Variable | Description | Default | Required |
|---|---|---|---|
| `MCP_SERVER_BASE_URL` | Public URL of this server. **Setting this enables OAuth.** | _(unset = no auth)_ | For OAuth |
| `DEX_ISSUER` | Dex's public issuer URL (must match `issuer` in Dex config) | `https://auth.longstorymedia.com` | For OAuth |
| `DEX_INTERNAL_URL` | In-cluster Dex URL for server-to-server calls (token exchange, JWKS) | `http://dex.auth.svc.cluster.local:5556` | For OAuth |
| `OAUTH_CLIENT_ID` | Dex static client ID | `gmail-mcp-client` | For OAuth |
| `OAUTH_JWT_SIGNING_KEY` | Secret for signing FastMCP-issued JWTs (required for public clients) | — | For OAuth |
| `GOOGLE_CREDENTIALS_JSON` | Google OAuth credentials JSON (Gmail API) | — | Always |
| `GMAIL_TOKENS_DIR` | Directory for persisted Gmail OAuth tokens | `~/.gmail-tokens` | No |
| `GMAIL_JOBS_DIR` | Directory for scheduled jobs state | `~/.gmail-jobs` | No |
| `MCP_TRANSPORT` | Transport mode: `http` or `stdio` | `http` | No |

## OAuth Configuration

### How It Works

The server uses FastMCP's [`OAuthProxy`](https://gofastmcp.com/servers/auth/oauth-proxy) to bridge MCP clients (which expect DCR) with Dex (which uses static client registration).

Key design points:
- **Split URLs**: The browser-facing authorization endpoint uses the public Dex issuer (`https://auth.longstorymedia.com`). Token exchange and JWKS verification use the internal k8s service (`http://dex.auth.svc.cluster.local:5556`).
- **Public client**: The Dex client is configured as `public: true` (no client secret). FastMCP uses `token_endpoint_auth_method="none"` and requires an explicit `jwt_signing_key` to sign its own JWTs.
- **Token factory**: MCP clients never receive Dex tokens directly. FastMCP issues its own JWTs, with the Dex token stored encrypted server-side.

### Dex Client Configuration

The `gmail-mcp-client` static client must exist in the Dex config (`k3s-cluster/auth/config.yaml`):

```yaml
staticClients:
  - id: gmail-mcp-client
    public: true
    name: "Gmail MCP Server Client"
    redirectURIs:
      - "http://localhost:8000/auth/callback"
      - "http://127.0.0.1:8000/auth/callback"
      - "http://mcp-server-gmail.llmmllab-mcp.svc.cluster.local:8000/auth/callback"
```

> The redirect path is `/auth/callback` (FastMCP's default). Do **not** add a `/mcp` prefix.

After changing Dex config, redeploy it:
```bash
cd k3s-cluster && make auth
```

## Tools

| Tool | Parameters | Description |
|---|---|---|
| `read_email` | `message_id` | Read full email by ID (sender, subject, date, HTML/text body) |
| `grep_email` | `query`, `pattern`, `max_results?`, `context?` | Search email bodies for a regex pattern with context lines |
| `search_emails` | `query`, `max_results?` | Search emails and return snippets + labels |
| `count_emails` | `query` | Count emails matching a Gmail query |
| `delete_emails` | `query`, `max_results?`, `dry_run?` | Move matching emails to trash |
| `add_label_to_emails` | `query`, `label_name`, `max_results?` | Apply a label to matching emails |
| `get_or_create_label` | `label_name`, `color?` | Get a label by name or create it |
| `create_label` | `label_name`, `color?` | Create a new Gmail label |
| `list_labels` | — | List all labels in the account |

## MCP Client Configuration

### Claude Code (stdio — local)

```json
{
  "mcpServers": {
    "gmail": {
      "command": "bash",
      "args": ["-c", "cd /path/to/mcp-server-gmail && MCP_TRANSPORT=stdio uv run python server.py"]
    }
  }
}
```

### Claude Code (HTTP — networked)

```json
{
  "mcpServers": {
    "gmail": {
      "type": "http",
      "url": "http://mcp-server-gmail.llmmllab-mcp.svc.cluster.local:8000/mcp"
    }
  }
}
```

## Project Structure

```
├── server.py           # FastMCP server, tool definitions, transport setup
├── gmail.py            # Gmail API service layer (GmailService context manager, Pydantic models)
├── oauth_provider.py   # OAuthProxy configuration for Dex
├── config.py           # Paths, scopes, constants
├── setup_oauth.py      # One-time Google OAuth credential flow
├── run.sh              # Convenience wrapper for stdio transport
├── Dockerfile          # Multi-arch production image (Python 3.12 + uv)
├── Makefile            # Dev, build, deploy, and k8s commands
├── pyproject.toml      # Python project metadata and dependencies
├── pyrightconfig.json  # Pyright type-checking config
└── k8s/
    ├── deployment.yaml # Deployment, Service, PVCs
    └── install.sh      # Full k8s install (build, secrets, apply)
```

## License

MIT
