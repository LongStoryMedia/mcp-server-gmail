# Gmail MCP Server

A FastMCP server that provides Gmail integration for AI assistants via the Model Context Protocol.

## Features

- Search emails
- Count emails
- Delete emails
- Label management
- OAuth 2.0 authentication via Dex

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌─────────────────┐
│  MCP Client  │────▶│ Gmail MCP    │────▶│  Dex (OAuth)    │
│  (Claude)    │     │  Server      │     │  Auth Server    │
└──────────────┘     └──────────────┘     └─────────────────┘
                              │
                              ▼
                     ┌─────────────────┐
                     │  Gmail API      │
                     └─────────────────┘
```

## Quick Start

### Local Development

1. **Set up OAuth credentials** (one-time):
   ```bash
   # Create .secrets directory and add credentials.json from Google Cloud Console
   mkdir -p .secrets
   cp /path/to/credentials.json .secrets/credentials.json
   
   # Run OAuth setup to generate token
   python setup_oauth.py
   ```

2. **Install dependencies**:
   ```bash
   uv sync
   ```

3. **Run the server**:
   ```bash
   # Without OAuth (local development only)
   uv run python server.py
   
   # With OAuth (production)
   MCP_SERVER_BASE_URL=http://localhost:8000 \
   DEX_SERVER=https://auth.longstorymedia.com \
   OAUTH_CLIENT_ID=gmail-mcp-client \
   uv run python server.py
   ```

### Kubernetes Deployment

1. **Add Dex OAuth client** to `k3s-cluster/auth/config.yaml`:
   ```yaml
   - id: gmail-mcp-client
     public: true
     name: "Gmail MCP Server Client"
     redirectURIs:
       - "http://localhost:8000/auth/callback"
   ```

2. **Build and push Docker image**:
   ```bash
   docker build -t 192.168.0.71:31500/mcp-server-gmail:latest .
   docker push 192.168.0.71:31500/mcp-server-gmail:latest
   ```

3. **Apply Kubernetes manifests**:
   ```bash
   kubectl apply -f k8s/deployment.yaml
   ```

4. **Verify deployment**:
   ```bash
   kubectl logs -n llmmllab-mcp -l app=mcp-server-gmail -f
   ```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `MCP_SERVER_BASE_URL` | Public URL of the MCP server | For OAuth |
| `DEX_SERVER` | Dex OAuth server URL | For OAuth |
| `OAUTH_CLIENT_ID` | OAuth client ID | For OAuth |
| `OAUTH_CLIENT_SECRET` | OAuth client secret | Optional |
| `GOOGLE_CREDENTIALS_JSON` | Gmail API credentials JSON | Always |

## OAuth Configuration

The server supports OAuth 2.0 authentication via Dex. To configure:

1. Add a new client to Dex (`k3s-cluster/auth/config.yaml`):
   ```yaml
   staticClients:
     - id: gmail-mcp-client
       public: true
       name: "Gmail MCP Server Client"
       redirectURIs:
         - "http://your-server:8000/auth/callback"
   ```

2. Restart Dex:
   ```bash
   kubectl rollout restart deployment/dex -n auth
   ```

3. Set environment variables in the deployment:
   ```yaml
   env:
     - name: MCP_SERVER_BASE_URL
       value: "http://your-server:8000"
     - name: DEX_SERVER
       value: "https://auth.longstorymedia.com"
     - name: OAUTH_CLIENT_ID
       value: "gmail-mcp-client"
   ```

## MCP Client Configuration

Add to your Claude Code settings:

```json
{
  "mcpServers": {
    "gmail": {
      "type": "http",
      "url": "http://your-server:8000/mcp"
    }
  }
}
```

## Tools

- `search_emails(query, max_results)` - Search for emails
- `count_emails(query)` - Count emails matching query
- `delete_emails(query, max_results, dry_run)` - Delete emails
- `add_label_to_emails(query, label_name, max_results)` - Add labels to emails
- `create_label(label_name, color)` - Create a new label
- `list_labels()` - List all labels

## License

MIT
