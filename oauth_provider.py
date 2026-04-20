"""
OAuth provider configuration for Gmail MCP Server using Dex as the identity provider.

This module sets up OIDCProxy to work with the existing Dex OIDC infrastructure.

Dex exposes a standard /.well-known/openid-configuration endpoint.  OIDCProxy
auto-discovers the authorization, token, and JWKS endpoints from it, and
properly handles the required `openid` scope that Dex mandates.

We fetch the OIDC config from the internal k8s URL (server-to-server) but the
discovered endpoints will use the public issuer URL (because Dex advertises
its `issuer` as the base), which is correct for browser redirects.
"""

from fastmcp.server.auth.oidc_proxy import OIDCProxy
from fastmcp.server.auth.providers.jwt import JWTVerifier

from config import (
    DEX_ISSUER,
    DEX_INTERNAL_URL,
    MCP_SERVER_BASE_URL,
    OAUTH_CLIENT_ID,
    OAUTH_JWT_SIGNING_KEY,
)


def create_oauth_provider() -> OIDCProxy:
    """
    Create an OIDCProxy configured to work with Dex.

    Configuration is loaded from config.py (driven by environment variables).
    """
    base_url = MCP_SERVER_BASE_URL or "http://localhost:8000"

    if not OAUTH_JWT_SIGNING_KEY:
        raise RuntimeError(
            "OAUTH_JWT_SIGNING_KEY must be set (required for public Dex clients "
            "that have no client_secret)"
        )

    # Custom token verifier using internal JWKS endpoint (server-to-server)
    # but validating against the public issuer claim.
    token_verifier = JWTVerifier(
        jwks_uri=f"{DEX_INTERNAL_URL}/keys",
        issuer=DEX_ISSUER,
        audience=OAUTH_CLIENT_ID,
        required_scopes=["openid"],
    )

    auth = OIDCProxy(
        # Fetch OIDC discovery doc from internal Dex URL (server-to-server).
        # The discovered auth endpoint will use the public issuer URL,
        # which is correct since the user's browser needs to reach Dex.
        config_url=f"{DEX_INTERNAL_URL}/.well-known/openid-configuration",
        client_id=OAUTH_CLIENT_ID,
        # Public client – no secret
        token_endpoint_auth_method="none",
        token_verifier=token_verifier,
        base_url=base_url,
        jwt_signing_key=OAUTH_JWT_SIGNING_KEY,
        # openid is mandatory for Dex; included in upstream authorization requests
        required_scopes=["openid"],
        allowed_client_redirect_uris=[
            "http://localhost:*",
            "http://127.0.0.1:*",
        ],
    )

    return auth
