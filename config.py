"""Configuration constants for Gmail MCP Server."""

import os
from pathlib import Path

# Base directory for this package
BASE_DIR = Path(__file__).parent

# Load environment variables from .env file if available
try:
    from dotenv import load_dotenv
    # Load from project directory explicitly
    env_path = BASE_DIR / ".env"
    load_dotenv(dotenv_path=env_path) if env_path.exists() else load_dotenv()
except ImportError:
    pass

# Directories for tokens and jobs
GMAIL_TOKENS_DIR = Path(os.environ.get("GMAIL_TOKENS_DIR", "~/.gmail-tokens")).expanduser()
GMAIL_JOBS_DIR = Path(os.environ.get("GMAIL_JOBS_DIR", "~/.gmail-jobs")).expanduser()

# File paths
CREDENTIALS_FILE = GMAIL_TOKENS_DIR / "credentials.json"
TOKEN_FILE = GMAIL_TOKENS_DIR / "token.json"
JOBS_FILE = GMAIL_JOBS_DIR / "jobs.json"

# OAuth scopes
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.labels",
]

# Job status constants
JOB_ENABLED = "enabled"
JOB_DISABLED = "disabled"
JOB_FAILED_COUNT_THRESHOLD = 5

# Server configuration
MCP_SERVER_BASE_URL = os.environ.get("MCP_SERVER_BASE_URL")
MCP_TRANSPORT = os.environ.get("MCP_TRANSPORT", "http")

# OAuth / Dex configuration
DEX_ISSUER = os.environ.get("DEX_ISSUER", "https://auth.longstorymedia.com")
DEX_INTERNAL_URL = os.environ.get(
    "DEX_INTERNAL_URL", "http://dex.auth.svc.cluster.local:5556"
)
OAUTH_CLIENT_ID = os.environ.get("OAUTH_CLIENT_ID", "gmail-mcp-client")
OAUTH_JWT_SIGNING_KEY = os.environ.get("OAUTH_JWT_SIGNING_KEY")


def ensure_jobs_dir() -> None:
    """Ensure the jobs directory exists."""
    GMAIL_JOBS_DIR.mkdir(parents=True, exist_ok=True)


def ensure_tokens_dir() -> None:
    """Ensure the tokens directory exists."""
    GMAIL_TOKENS_DIR.mkdir(parents=True, exist_ok=True)
