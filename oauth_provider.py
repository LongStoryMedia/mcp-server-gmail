"""
OAuth provider configuration for Gmail MCP Server using Dex as the identity provider.

This module sets up OAuthProxy to work with the existing Dex infrastructure.

Dex's issuer (public URL used in JWT tokens) differs from the internal k8s
service URL.  The browser-facing authorization endpoint must use the public
issuer so the user's browser can reach Dex.  The token and JWKS endpoints are
called server-to-server and should use the in-cluster DNS name.
"""

from fastmcp.server.auth import OAuthProxy
from fastmcp.server.auth.providers.jwt import JWTVerifier

from config import (
    DEX_ISSUER,
    DEX_INTERNAL_URL,
    MCP_SERVER_BASE_URL,
    OAUTH_CLIENT_ID,
    OAUTH_JWT_SIGNING_KEY,
)


def create_oauth_provider() -> OAuthProxy:
    """
    Create an OAuthProxy configured to work with Dex.

    Configuration is loaded from config.py (driven by environment variables).
    """
    base_url = MCP_SERVER_BASE_URL or "http://localhost:8000"

    if not OAUTH_JWT_SIGNING_KEY:
        raise RuntimeError(
            "OAUTH_JWT_SIGNING_KEY must be set (required for public Dex clients "
            "that have no client_secret)"
        )

    # Validate upstream tokens (Dex JWTs) using the internal JWKS endpoint
    # but matching the public issuer claim.
    # NOTE: Do NOT set required_scopes here. This verifier validates the
    # upstream Dex token during code exchange, but its required_scopes also
    # propagate to the FastMCP-issued JWT validation. Dex may not include
    # "openid" in the token response's scope field, causing FastMCP's own
    # JWT to lack that scope and fail validation on subsequent requests.
    # The openid scope requirement for Dex's auth endpoint is handled by
    # extra_authorize_params below.
    token_verifier = JWTVerifier(
        jwks_uri=f"{DEX_INTERNAL_URL}/keys",
        issuer=DEX_ISSUER,
        audience=OAUTH_CLIENT_ID,
    )

    auth = OAuthProxy(
        # Browser-facing: user's browser is redirected to the public Dex URL
        upstream_authorization_endpoint=f"{DEX_ISSUER}/auth",
        # Server-to-server: exchange auth code for tokens via internal URL
        upstream_token_endpoint=f"{DEX_INTERNAL_URL}/token",
        upstream_client_id=OAUTH_CLIENT_ID,
        # Public client – no secret sent to Dex
        token_endpoint_auth_method="none",
        token_verifier=token_verifier,
        base_url=base_url,
        # Required because there is no upstream_client_secret to derive from
        jwt_signing_key=OAUTH_JWT_SIGNING_KEY,
        # Advertise openid scope to MCP clients
        valid_scopes=["openid"],
        # Force openid scope on EVERY upstream authorization request.
        # This is critical: FastMCP uses client-requested scopes first,
        # and only falls back to required_scopes if the client sends none.
        # extra_authorize_params overrides after scope calculation, ensuring
        # Dex always receives scope=openid regardless of what the client sent.
        extra_authorize_params={"scope": "openid"},
        allowed_client_redirect_uris=[
            "http://localhost:*",
            "http://127.0.0.1:*",
        ],
    )

    return auth
