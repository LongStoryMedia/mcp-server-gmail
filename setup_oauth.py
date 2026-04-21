#!/usr/bin/env python3
"""
OAuth setup script for Gmail MCP Server.

This script performs the OAuth 2.0 flow to get initial credentials
and saves them for use by the Gmail MCP server.

Usage:
    python setup_oauth.py

This will open a browser for OAuth authentication. After successful
authentication, the tokens will be saved to:
- .secrets/token.json (for local development)
- K8s secret gmail-secrets (for Kubernetes deployment)
"""

import pickle
import subprocess
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

# OAuth scopes
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.labels",
]


def main():
    """Run the OAuth flow and save tokens."""
    tokens_dir = Path(__file__).parent / ".secrets"
    tokens_dir.mkdir(parents=True, exist_ok=True)

    credentials_file = tokens_dir / "credentials.json"
    token_file = tokens_dir / "token.json"

    print("=== Gmail MCP Server OAuth Setup ===")
    print()

    if not credentials_file.exists():
        print("ERROR: credentials.json not found!")
        print(f"Please place your Google OAuth credentials file at: {credentials_file}")
        print()
        print("To get credentials:")
        print("1. Go to https://console.cloud.google.com/")
        print("2. Create a project or select existing one")
        print("3. Enable Gmail API")
        print("4. Create OAuth 2.0 credentials (Desktop app)")
        print("5. Download the JSON file and save as credentials.json")
        return 1

    print(f"Found credentials file: {credentials_file}")
    print(f"Token file: {token_file}")
    print()

    # Always force a fresh OAuth consent flow with prompt=consent.
    # This is critical because:
    # 1. Refreshing a token does NOT add new scopes
    # 2. Without prompt=consent, Google may skip the consent screen
    #    and return the same refresh_token with only the originally
    #    granted scopes (e.g. gmail.readonly only)
    # 3. The user MUST see the consent screen and explicitly approve
    #    ALL requested scopes at once
    print("Starting OAuth flow...")
    print("A browser window should open for authentication.")
    print("You must approve ALL requested scopes on the consent screen.")
    print()

    flow = InstalledAppFlow.from_client_secrets_file(
        str(credentials_file), SCOPES,
        # Force consent screen every time so user approves all scopes
        redirect_uri="http://localhost:8080",
    )
    # Use prompt=consent to force the consent screen even if user
    # already granted consent before. access_type=offline ensures
    # a refresh_token is returned.
    creds = flow.run_local_server(
        host="localhost",
        port=8080,
        access_type="offline",
        prompt="consent",
    )

    with open(token_file, "wb") as f:
        pickle.dump(creds, f)

    print()
    print("=== OAuth Setup Complete ===")
    print(f"Token saved to: {token_file}")
    print(f"Scopes granted: {creds.scopes}")
    print()

    # Try to update K8s secret
    print("Attempting to update K8s secret...")
    try:
        # Create secret from local files
        result = subprocess.run(
            [
                "kubectl", "create", "secret", "generic", "gmail-secrets",
                "--from-file=token.json=" + str(token_file),
                "--from-file=credentials.json=" + str(credentials_file),
                "-n", "llmmllab-mcp",
                "--dry-run=client", "-o", "yaml",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        # Apply the secret
        apply_result = subprocess.run(
            ["kubectl", "apply", "-f", "-"],
            input=result.stdout,
            capture_output=True,
            text=True,
            check=True,
        )
        print(f"K8s secret updated: {apply_result.stdout.strip()}")
    except subprocess.CalledProcessError as e:
        print(f"Warning: Could not update K8s secret: {e}")
        print("To manually update, run:")
        print(f"  kubectl create secret generic gmail-secrets \\")
        print(f"    --from-file=token.json={token_file} \\")
        print(f"    --from-file=credentials.json={credentials_file} \\")
        print(f"    -n llmmllab-mcp \\")
        print(f"    --dry-run=client -o yaml | kubectl apply -f -")
    except FileNotFoundError:
        print("Warning: kubectl not found. Skipping K8s secret update.")

    print()
    print("The Gmail MCP Server can now use these credentials.")

    return 0


if __name__ == "__main__":
    exit(main())
