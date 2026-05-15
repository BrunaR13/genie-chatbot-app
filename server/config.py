import os
from databricks.sdk import WorkspaceClient

# Detect environment
IS_DATABRICKS_APP = bool(os.environ.get("DATABRICKS_APP_NAME"))

def get_workspace_client() -> WorkspaceClient:
    """Get authenticated WorkspaceClient."""
    if IS_DATABRICKS_APP:
        # Remote: Uses auto-injected service principal credentials
        return WorkspaceClient()
    else:
        # Local: Uses Databricks CLI profile
        profile = os.environ.get("DATABRICKS_PROFILE", "fevm-bruna-robledo-demo-env")
        return WorkspaceClient(profile=profile)

def get_workspace_host() -> str:
    """Get workspace host URL with https:// prefix."""
    if IS_DATABRICKS_APP:
        host = os.environ.get("DATABRICKS_HOST", "")
        if host and not host.startswith("http"):
            host = f"https://{host}"
        return host
    client = get_workspace_client()
    return client.config.host
