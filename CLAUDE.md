## Architecture

**Core Components:**
- `server.py` - FastMCP server initialization with HTTP/SSE transport on port 8000
- `gmail.py` - Gmail API service layer with `GmailService` context manager and Pydantic models
- `config.py` - Configuration constants, OAuth scopes, and path management
- `setup_oauth.py` - Standalone OAuth 2.0 flow script for initial credentials setup

**Pydantic Models (`gmail.py`):**
- `Message` - Email message with id, threadId, labelIds, snippet, payload, etc.
- `MessagePart` - Message body parts with headers, mimeType, filename, body
- `MessagePartHeader` - Individual header name/value pair
- `MessagePartBody` - Attachment body with attachmentId, size, data
- `ListMessagesResponse` - Paginated message list with nextPageToken
- `Label` - Gmail label with id, name, type, color
- `ModifyMessageRequest` - Request to add/remove label IDs

**Tools (`tools/`):**
Each tool uses `@mcp.tool()` decorator and `GmailService` context manager:
- `count.py` - `count_emails(query)` - Count emails matching query
- `search.py` - `search_emails(query, max_results)` - Search and return email details
- `delete.py` - `delete_emails(query, max_results, dry_run)` - Delete emails
- `label.py` - Label management tools:
  - `add_label_to_emails(query, label_name, max_results)`
  - `get_or_create_label_tool(label_name, color)`
  - `create_label(label_name, color)`
  - `list_labels()`

**GmailService Methods:**
- `get_messages(query, page_token, max_results)` - List messages with pagination
- `get_message(msg_id)` - Get full message details
- `list_labels()` - List all labels
- `get_label_by_name(label_name)` - Find label by name
- `create_label(label_name, color)` - Create new label
- `get_or_create_label(label_name, color)` - Get or create label
- `modify_messages(message_ids, add_label_ids)` - Add labels to messages
- `delete_messages(message_ids)` - Delete messages by ID

**Data Flow:**
1. MCP client sends request → FastMCP server
2. Server routes to registered tool via `@mcp.tool()` decorator
3. Tool uses `GmailService` context manager (auto-authenticates)
4. Gmail API returns data → Pydantic models validate → response returned

## Kubernetes Deployment

**Namespace:** `llmmllab`

**Key Resources:**
- Deployment with persistent volumes for tokens (`gmail-tokens-pvc`) and jobs (`gmail-jobs-pvc`)
- Secrets mounted from `.secrets/credentials.json`
- ARM64 node selector required
- Image: `192.168.0.71:31500/mcp-server-gmail:latest`

## Development Commands

**Install dependencies:**
```bash
uv sync
```

**Run OAuth setup:**
```bash
python setup_oauth.py
```
Requires `.secrets/credentials.json` from Google Cloud Console.

**Build Docker image:**
```bash
docker build -t 192.168.0.71:31500/mcp-server-gmail:latest .
```

**Push to registry:**
```bash
docker push 192.168.0.71:31500/mcp-server-gmail:latest
```

**Kubernetes installation:**
```bash
kubectl apply -f k8s/deployment.yaml
```

**View logs:**
```bash
kubectl logs -n llmmllab -l app=mcp-server-gmail -f
```

## OAuth Credentials Setup

1. Go to https://console.cloud.google.com/
2. Create project or select existing
3. Enable Gmail API
4. Create OAuth 2.0 credentials (Desktop app)
5. Download JSON and save as `.secrets/credentials.json`
6. Run `python setup_oauth.py` to complete authentication
