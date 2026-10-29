"""Custom sources management endpoints."""

import asyncio
import hashlib
import hmac
import importlib.util
import logging
import os
import re
import shutil
import zipfile
from io import BytesIO
from typing import Any

from fastapi import APIRouter, BackgroundTasks, File, Header, HTTPException, Request, UploadFile
from pydantic import BaseModel

from bizon_platform.settings import settings

router = APIRouter(prefix="/custom-sources", tags=["custom-sources"])
logger = logging.getLogger(__name__)

# Timeout for connection checks (in seconds)
CHECK_TIMEOUT_SECONDS = 30


class SourceCodeResponse(BaseModel):
    """Response containing source code."""

    name: str
    code: str
    file_path: str


class ConfigFieldSchema(BaseModel):
    """Schema for a single config field."""

    name: str
    type: str  # "string", "integer", "number", "boolean"
    required: bool
    default: Any | None = None
    description: str | None = None
    is_secret: bool = False  # True for fields containing "key", "secret", "password", "token"


class ConfigSchemaResponse(BaseModel):
    """Response containing config schema for a custom source."""

    source_name: str
    fields: list[ConfigFieldSchema]


class TestConnectionRequest(BaseModel):
    """Request to test a custom source connection."""

    stream: str
    config: dict[str, Any] = {}  # Additional config fields


class TestConnectionResponse(BaseModel):
    """Response from connection test."""

    success: bool
    message: str


class UploadResponse(BaseModel):
    """Response from uploading a source."""

    name: str
    file_path: str
    streams: list[str]
    message: str


class DeleteResponse(BaseModel):
    """Response from deleting a source."""

    message: str


class GitSyncResponse(BaseModel):
    """Response from git sync operation."""

    success: bool
    message: str
    commit_hash: str | None = None
    files_updated: int = 0
    synced_at: str | None = None


class GitSyncStatusResponse(BaseModel):
    """Response for git sync status/configuration."""

    enabled: bool
    repo_url: str | None = None
    branch: str = "main"
    path: str = "custom_sources"
    webhook_configured: bool = False


class GitSyncWebhookResponse(BaseModel):
    """Response from git sync webhook."""

    status: str  # "sync_triggered", "skipped", "error"
    message: str


_SOURCE_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")


def _source_dir(name: str) -> str:
    """Return the directory of a custom source, rejecting names that could escape the sources dir."""
    if not _SOURCE_NAME_RE.match(name):
        raise HTTPException(status_code=400, detail=f"Invalid source name '{name}'")
    return os.path.join(settings.custom_sources_dir, name)


def _get_source_class(source_name: str):
    """Load and return the source class from a custom source."""
    from bizon.source.source import AbstractSource

    source_dir = _source_dir(source_name)
    source_file = os.path.join(source_dir, "source.py")

    if not os.path.exists(source_file):
        raise HTTPException(status_code=404, detail=f"Custom source '{source_name}' not found")

    spec = importlib.util.spec_from_file_location(f"custom_source_{source_name}", source_file)
    if spec is None or spec.loader is None:
        raise HTTPException(status_code=500, detail=f"Failed to load source module for '{source_name}'")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Find the source class
    source_class = None
    for name, obj in vars(module).items():
        if isinstance(obj, type) and issubclass(obj, AbstractSource) and obj != AbstractSource:
            source_class = obj
            break

    if source_class is None:
        raise HTTPException(status_code=500, detail=f"No valid source class found in '{source_name}'")

    return source_class


@router.get("/{name}/code", response_model=SourceCodeResponse)
async def get_source_code(name: str) -> SourceCodeResponse:
    """Get the source code for a custom source."""
    source_dir = _source_dir(name)
    source_file = os.path.join(source_dir, "source.py")

    if not os.path.exists(source_file):
        raise HTTPException(status_code=404, detail=f"Custom source '{name}' not found")

    try:
        with open(source_file, "r", encoding="utf-8") as f:
            code = f.read()

        docker_path = f"/custom_sources/{name}/source.py"

        return SourceCodeResponse(
            name=name,
            code=code,
            file_path=docker_path,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read source code: {str(e)}")


# Base SourceConfig fields to exclude from custom config schema
_BASE_SOURCE_CONFIG_FIELDS = {
    "name",
    "stream",
    "source_file_path",
    "authentication",
    "sync_mode",
    "cursor_field",
}

# Keywords that indicate a field contains sensitive data
_SECRET_KEYWORDS = {"key", "secret", "password", "token", "credential", "auth"}


def _is_secret_field(field_name: str) -> bool:
    """Check if a field name suggests it contains sensitive data."""
    field_lower = field_name.lower()
    return any(keyword in field_lower for keyword in _SECRET_KEYWORDS)


def _json_type_to_simple(json_type: str | list | None, format_hint: str | None = None) -> str:
    """Convert JSON Schema type to simple type string."""
    if isinstance(json_type, list):
        # Handle nullable types like ["string", "null"]
        types = [t for t in json_type if t != "null"]
        json_type = types[0] if types else "string"

    if json_type == "integer":
        return "integer"
    elif json_type == "number":
        return "number"
    elif json_type == "boolean":
        return "boolean"
    else:
        return "string"


@router.get("/{name}/config-schema", response_model=ConfigSchemaResponse)
async def get_config_schema(name: str) -> ConfigSchemaResponse:
    """Get the config schema for a custom source, excluding base SourceConfig fields."""
    try:
        source_class = _get_source_class(name)
        config_class = source_class.get_config_class()

        # Get JSON schema from Pydantic model
        schema = config_class.model_json_schema()
        properties = schema.get("properties", {})
        required_fields = set(schema.get("required", []))

        # Handle $defs for referenced schemas
        defs = schema.get("$defs", {})

        fields: list[ConfigFieldSchema] = []

        for field_name, field_info in properties.items():
            # Skip base SourceConfig fields
            if field_name in _BASE_SOURCE_CONFIG_FIELDS:
                continue

            # Handle $ref references
            if "$ref" in field_info:
                ref_path = field_info["$ref"]
                ref_name = ref_path.split("/")[-1]
                if ref_name in defs:
                    field_info = defs[ref_name]

            # Handle anyOf (often used for Optional types)
            if "anyOf" in field_info:
                for option in field_info["anyOf"]:
                    if option.get("type") != "null":
                        field_info = {**field_info, **option}
                        break

            field_type = _json_type_to_simple(field_info.get("type"), field_info.get("format"))

            fields.append(
                ConfigFieldSchema(
                    name=field_name,
                    type=field_type,
                    required=field_name in required_fields,
                    default=field_info.get("default"),
                    description=field_info.get("description"),
                    is_secret=_is_secret_field(field_name),
                )
            )

        return ConfigSchemaResponse(source_name=name, fields=fields)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get config schema: {str(e)}")


def _test_connection_sync(source_name: str, stream: str, config_values: dict[str, Any]) -> TestConnectionResponse:
    """Synchronous connection test implementation."""
    try:
        source_class = _get_source_class(source_name)
        config_class = source_class.get_config_class()

        # Check if stream is valid
        available_streams = source_class.streams()
        if stream not in available_streams:
            return TestConnectionResponse(
                success=False,
                message=f"Stream '{stream}' not found. Available: {', '.join(available_streams)}",
            )

        # Create config and source instance
        docker_path = f"/custom_sources/{source_name}/source.py"
        config_dict = {
            "name": source_name,
            "stream": stream,
            "source_file_path": docker_path,
            **config_values,  # Merge user-provided config values
        }
        config = config_class(**config_dict)
        source_instance = source_class(config=config)

        # Test connection
        success, error_message = source_instance.check_connection()

        if success:
            return TestConnectionResponse(success=True, message="Connection successful")
        else:
            return TestConnectionResponse(
                success=False,
                message=error_message or "Connection check failed",
            )

    except HTTPException:
        raise
    except Exception as e:
        return TestConnectionResponse(success=False, message=f"Test failed: {str(e)}")


@router.post("/{name}/test", response_model=TestConnectionResponse)
async def test_connection(name: str, request: TestConnectionRequest) -> TestConnectionResponse:
    """Test connection for a custom source stream."""
    try:
        result = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(None, _test_connection_sync, name, request.stream, request.config),
            timeout=CHECK_TIMEOUT_SECONDS,
        )
        return result
    except asyncio.TimeoutError:
        return TestConnectionResponse(
            success=False,
            message=f"Connection check timed out after {CHECK_TIMEOUT_SECONDS} seconds",
        )
    except HTTPException:
        raise
    except Exception as e:
        return TestConnectionResponse(success=False, message=f"Test failed: {str(e)}")


@router.post("/upload", response_model=UploadResponse)
async def upload_source(file: UploadFile = File(...)) -> UploadResponse:
    """Upload a new custom source.

    Accepts either:
    - A .py file (will create a directory named after the file)
    - A .zip file containing a directory with source.py
    """
    from bizon.source.source import AbstractSource

    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    content = await file.read()

    # Ensure custom sources directory exists
    os.makedirs(settings.custom_sources_dir, exist_ok=True)

    if file.filename.endswith(".py"):
        # Single Python file upload
        source_name = file.filename.replace(".py", "").replace("-", "_").lower()
        source_dir = _source_dir(source_name)

        if os.path.exists(source_dir):
            raise HTTPException(status_code=400, detail=f"Source '{source_name}' already exists")

        os.makedirs(source_dir)
        source_file = os.path.join(source_dir, "source.py")

        try:
            with open(source_file, "wb") as f:
                f.write(content)
        except Exception as e:
            shutil.rmtree(source_dir, ignore_errors=True)
            raise HTTPException(status_code=500, detail=f"Failed to write source file: {str(e)}")

    elif file.filename.endswith(".zip"):
        # Zip file upload
        try:
            with zipfile.ZipFile(BytesIO(content)) as zf:
                # Find the source.py file
                source_py_path = None
                for name in zf.namelist():
                    if name.endswith("source.py") and not name.startswith("__"):
                        source_py_path = name
                        break

                if not source_py_path:
                    raise HTTPException(status_code=400, detail="No source.py found in zip file")

                # Determine source name from path
                parts = source_py_path.split("/")
                if len(parts) > 1:
                    source_name = parts[0].replace("-", "_").lower()
                else:
                    source_name = file.filename.replace(".zip", "").replace("-", "_").lower()

                source_dir = _source_dir(source_name)

                if os.path.exists(source_dir):
                    raise HTTPException(status_code=400, detail=f"Source '{source_name}' already exists")

                os.makedirs(source_dir)

                # Extract source.py
                source_file = os.path.join(source_dir, "source.py")
                with zf.open(source_py_path) as src, open(source_file, "wb") as dst:
                    dst.write(src.read())

        except zipfile.BadZipFile:
            raise HTTPException(status_code=400, detail="Invalid zip file")
        except HTTPException:
            raise
        except Exception as e:
            if "source_dir" in locals():
                shutil.rmtree(source_dir, ignore_errors=True)
            raise HTTPException(status_code=500, detail=f"Failed to extract zip: {str(e)}")
    else:
        raise HTTPException(status_code=400, detail="File must be .py or .zip")

    # Validate the uploaded source
    try:
        source_file_path = os.path.join(source_dir, "source.py")
        spec = importlib.util.spec_from_file_location(f"custom_source_{source_name}", source_file_path)
        if spec is None or spec.loader is None:
            raise Exception("Failed to load module spec")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Find the source class
        source_class = None
        for attr_name, obj in vars(module).items():
            if isinstance(obj, type) and issubclass(obj, AbstractSource) and obj != AbstractSource:
                source_class = obj
                break

        if source_class is None:
            raise Exception("No valid source class found (must inherit from AbstractSource)")

        streams = source_class.streams()

    except Exception as e:
        shutil.rmtree(source_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=f"Invalid source: {str(e)}")

    docker_path = f"/custom_sources/{source_name}/source.py"

    return UploadResponse(
        name=source_name,
        file_path=docker_path,
        streams=streams,
        message=f"Successfully uploaded source '{source_name}'",
    )


@router.delete("/{name}", response_model=DeleteResponse)
async def delete_source(name: str) -> DeleteResponse:
    """Delete a custom source."""
    source_dir = _source_dir(name)

    if not os.path.exists(source_dir):
        raise HTTPException(status_code=404, detail=f"Custom source '{name}' not found")

    try:
        shutil.rmtree(source_dir)
        return DeleteResponse(message=f"Successfully deleted source '{name}'")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete source: {str(e)}")


@router.get("/git-sync/status", response_model=GitSyncStatusResponse)
async def get_git_sync_status() -> GitSyncStatusResponse:
    """Get git sync configuration status."""
    return GitSyncStatusResponse(
        enabled=settings.git_sync_enabled,
        repo_url=settings.git_sync_repo_url if settings.git_sync_enabled else None,
        branch=settings.git_sync_branch,
        path=settings.git_sync_path,
        webhook_configured=bool(settings.git_sync_webhook_secret),
    )


@router.post("/git-sync", response_model=GitSyncResponse)
async def sync_from_git() -> GitSyncResponse:
    """Sync custom sources from the configured git repository."""
    from bizon_platform.git_sync import sync_from_git as do_sync

    if not settings.git_sync_enabled:
        raise HTTPException(status_code=400, detail="Git sync is not enabled")

    if not settings.git_sync_repo_url:
        raise HTTPException(status_code=400, detail="Git sync repo URL not configured")

    # Run sync in executor to not block
    result = await asyncio.get_event_loop().run_in_executor(None, do_sync)

    return GitSyncResponse(
        success=result.success,
        message=result.message,
        commit_hash=result.commit_hash,
        files_updated=result.files_updated,
        synced_at=result.synced_at.isoformat() if result.synced_at else None,
    )


def _verify_github_signature(payload: bytes, signature: str | None, secret: str) -> bool:
    """Verify GitHub webhook signature (HMAC-SHA256).

    GitHub sends the signature in the format: sha256=<hex-digest>
    """
    if not signature:
        return False

    if not signature.startswith("sha256="):
        return False

    expected_signature = signature[7:]  # Remove "sha256=" prefix
    computed_signature = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected_signature, computed_signature)


def _verify_gitlab_signature(payload: bytes, token: str | None, secret: str) -> bool:
    """Verify GitLab webhook token.

    GitLab sends the secret token in the X-Gitlab-Token header.
    """
    if not token:
        return False
    return hmac.compare_digest(token, secret)


def _run_sync_background() -> None:
    """Run git sync in background (for use with BackgroundTasks)."""
    from bizon_platform.git_sync import sync_from_git as do_sync

    result = do_sync()
    if result.success:
        logger.info(f"Webhook-triggered sync complete: {result.message}")
    else:
        logger.error(f"Webhook-triggered sync failed: {result.message}")


@router.post("/git-sync/webhook", response_model=GitSyncWebhookResponse)
async def git_sync_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: str | None = Header(None),
    x_gitlab_token: str | None = Header(None),
    x_github_event: str | None = Header(None),
    x_gitlab_event: str | None = Header(None),
) -> GitSyncWebhookResponse:
    """Webhook endpoint for GitHub/GitLab push events.

    Configure this URL in your GitHub/GitLab repository webhook settings:
    - URL: https://your-domain/api/custom-sources/git-sync/webhook
    - Content type: application/json
    - Secret: Set GIT_SYNC_WEBHOOK_SECRET env var to the same value
    - Events: Push events only

    Supports both GitHub and GitLab webhooks.
    """
    # Check if webhook is configured
    if not settings.git_sync_webhook_secret:
        raise HTTPException(status_code=400, detail="Webhook secret not configured")

    if not settings.git_sync_enabled:
        raise HTTPException(status_code=400, detail="Git sync is not enabled")

    # Read request body
    body = await request.body()

    # Verify signature (GitHub or GitLab)
    is_github = x_hub_signature_256 is not None or x_github_event is not None
    is_gitlab = x_gitlab_token is not None or x_gitlab_event is not None

    if is_github:
        if not _verify_github_signature(body, x_hub_signature_256, settings.git_sync_webhook_secret):
            logger.warning("GitHub webhook signature verification failed")
            raise HTTPException(status_code=401, detail="Invalid signature")
    elif is_gitlab:
        if not _verify_gitlab_signature(body, x_gitlab_token, settings.git_sync_webhook_secret):
            logger.warning("GitLab webhook token verification failed")
            raise HTTPException(status_code=401, detail="Invalid token")
    else:
        raise HTTPException(status_code=400, detail="Unknown webhook source")

    # Parse payload
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Extract branch reference
    # GitHub: {"ref": "refs/heads/main", ...}
    # GitLab: {"ref": "refs/heads/main", ...}
    ref = payload.get("ref", "")
    expected_ref = f"refs/heads/{settings.git_sync_branch}"

    if ref != expected_ref:
        branch_name = ref.replace("refs/heads/", "") if ref.startswith("refs/heads/") else ref
        logger.info(f"Webhook received for branch '{branch_name}', skipping (configured: {settings.git_sync_branch})")
        return GitSyncWebhookResponse(
            status="skipped",
            message=f"Push to '{branch_name}' ignored, only syncing '{settings.git_sync_branch}'",
        )

    # Trigger sync in background
    logger.info(f"Webhook received for {settings.git_sync_branch}, triggering sync")
    background_tasks.add_task(_run_sync_background)

    return GitSyncWebhookResponse(
        status="sync_triggered",
        message=f"Sync triggered for branch '{settings.git_sync_branch}'",
    )
