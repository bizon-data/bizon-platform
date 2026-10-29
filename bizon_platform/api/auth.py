"""Optional basic authentication for bizon-platform.

When ADMIN_PASSWORD is set, all API endpoints (except health check) require
HTTP Basic Authentication with any username and the configured password.
The git sync webhook is also exempt: it authenticates with its own signature.

This is intended for simple deployments without a reverse proxy.
For production, consider using a reverse proxy (nginx, Cloudflare, etc.)
with proper authentication.
"""

import secrets

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from bizon_platform.settings import settings

security = HTTPBasic(auto_error=False)

UNAUTHENTICATED_PATHS = {
    "/api/health",
    # GitHub/GitLab can't send Basic credentials; the route verifies GIT_SYNC_WEBHOOK_SECRET instead.
    "/api/custom-sources/git-sync/webhook",
}


async def optional_auth(
    request: Request,
    credentials: HTTPBasicCredentials | None = Depends(security),
) -> None:
    """Verify basic auth credentials if ADMIN_PASSWORD is configured.

    If ADMIN_PASSWORD is not set, this dependency does nothing (no auth required).
    If ADMIN_PASSWORD is set, requests must include valid Basic Auth credentials.

    The health check endpoint (/api/health) is always accessible without auth.
    """
    # No auth required if password not configured
    if not settings.admin_password:
        return

    if request.url.path in UNAUTHENTICATED_PATHS:
        return

    # Require valid credentials
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )

    # Constant-time comparison to prevent timing attacks
    password_valid = secrets.compare_digest(
        credentials.password.encode("utf-8"),
        settings.admin_password.encode("utf-8"),
    )

    if not password_valid:
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
