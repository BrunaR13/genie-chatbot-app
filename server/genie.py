import os
import sys
import time
import requests
from typing import Optional
from .config import get_workspace_client, get_workspace_host, IS_DATABRICKS_APP

# Import settings
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from settings import DEFAULT_GENIE_SPACES, GENIE_TIMEOUT_SECONDS


def _get_headers(user_token: Optional[str] = None) -> dict:
    """Get headers for API requests, using user token if available."""
    if user_token:
        return {"Authorization": f"Bearer {user_token}"}
    # Fall back to service principal
    client = get_workspace_client()
    auth_headers = client.config.authenticate()
    return dict(auth_headers) if auth_headers else {}


def _make_request(method: str, path: str, user_token: Optional[str] = None, body: dict = None) -> dict:
    """Make an API request using the user's token or service principal."""
    host = get_workspace_host()
    url = f"{host}{path}"
    headers = _get_headers(user_token)
    headers["Content-Type"] = "application/json"

    if method == "GET":
        response = requests.get(url, headers=headers)
    elif method == "POST":
        response = requests.post(url, headers=headers, json=body)
    else:
        raise ValueError(f"Unsupported method: {method}")

    response.raise_for_status()
    return response.json()


def get_current_user(user_token: Optional[str] = None) -> dict:
    """Get information about the current user."""
    try:
        response = _make_request("GET", "/api/2.0/preview/scim/v2/Me", user_token)
        return {
            "email": response.get("userName", ""),
            "name": response.get("displayName", response.get("userName", ""))
        }
    except Exception as e:
        print(f"Error getting current user: {e}")
        return {"email": "unknown", "name": "Unknown User"}


def list_genie_spaces(user_token: Optional[str] = None) -> list[dict]:
    """List all available Genie spaces using REST API."""
    try:
        response = _make_request("GET", "/api/2.0/genie/spaces", user_token)

        spaces = []
        for space in response.get("spaces", []):
            spaces.append({
                "space_id": space.get("space_id", ""),
                "title": space.get("title", ""),
                "description": space.get("description", "")
            })
        return spaces
    except Exception as e:
        # Fallback: return default spaces from settings if API fails
        print(f"Error listing spaces: {e}")
        return DEFAULT_GENIE_SPACES


def _get_query_result(
    space_id: str,
    conversation_id: str,
    message_id: str,
    attachment_id: str,
    user_token: Optional[str] = None
) -> dict:
    """
    Fetch query results using the attachment_id.

    According to docs: GET /api/2.0/genie/spaces/{space_id}/conversations/{conversation_id}/messages/{message_id}/query-result/{attachment_id}
    """
    try:
        response = _make_request(
            "GET",
            f"/api/2.0/genie/spaces/{space_id}/conversations/{conversation_id}/messages/{message_id}/query-result/{attachment_id}",
            user_token
        )
        return response
    except Exception as e:
        print(f"Error fetching query result for attachment {attachment_id}: {e}")
        return {}


def ask_genie(
    space_id: str,
    question: str,
    conversation_id: Optional[str] = None,
    timeout_seconds: int = GENIE_TIMEOUT_SECONDS,
    user_token: Optional[str] = None
) -> dict:
    """
    Ask a question to a Genie space and get the response using REST API.

    Args:
        space_id: The Genie space ID
        question: The question to ask
        conversation_id: Optional conversation ID for follow-up questions
        timeout_seconds: Maximum time to wait for response
        user_token: Optional user OAuth token for on-behalf-of-user requests

    Returns:
        Dictionary with the response data
    """
    result = {
        "conversation_id": "",
        "message_id": "",
        "status": "UNKNOWN",
        "question": question,
        "sql": None,
        "description": None,
        "columns": [],
        "data": [],
        "row_count": 0,
        "text_response": None,
        "error": None
    }

    try:
        # Start conversation
        if conversation_id:
            # Continue existing conversation
            start_response = _make_request(
                "POST",
                f"/api/2.0/genie/spaces/{space_id}/conversations/{conversation_id}/messages",
                user_token,
                body={"content": question}
            )
            result["conversation_id"] = conversation_id
        else:
            # Start new conversation
            start_response = _make_request(
                "POST",
                f"/api/2.0/genie/spaces/{space_id}/start-conversation",
                user_token,
                body={"content": question}
            )
            result["conversation_id"] = start_response.get("conversation_id", "")

        result["message_id"] = start_response.get("message_id", "")

        # Poll for completion
        poll_interval = 2
        elapsed = 0
        conv_id = result["conversation_id"]
        msg_id = result["message_id"]
        message_response = {}

        while elapsed < timeout_seconds:
            message_response = _make_request(
                "GET",
                f"/api/2.0/genie/spaces/{space_id}/conversations/{conv_id}/messages/{msg_id}",
                user_token
            )

            status = message_response.get("status", "UNKNOWN")
            result["status"] = status

            if status in ["COMPLETED", "FAILED", "CANCELLED"]:
                break

            time.sleep(poll_interval)
            elapsed += poll_interval

        # Parse attachments for query results
        attachments = message_response.get("attachments", [])

        for attachment in attachments:
            # Get attachment ID for fetching results
            attachment_id = attachment.get("attachment_id") or attachment.get("id")

            if "query" in attachment:
                query_info = attachment["query"]
                result["sql"] = query_info.get("query", "")
                result["description"] = query_info.get("description", "")

                # Method 1: Try to get result data from query_info.result (inline data)
                query_result = query_info.get("result", {})
                if query_result:
                    columns = query_result.get("columns", [])
                    if columns:
                        result["columns"] = [col.get("name", "") if isinstance(col, dict) else str(col) for col in columns]
                    data_array = query_result.get("data_array", [])
                    if data_array:
                        result["data"] = data_array
                        result["row_count"] = len(data_array)

                # Method 2: Fetch using the query-result endpoint with attachment_id
                if not result["data"] and attachment_id:
                    query_result_response = _get_query_result(
                        space_id, conv_id, msg_id, attachment_id, user_token
                    )

                    if query_result_response:
                        # Structure: statement_response.manifest.schema.columns + statement_response.result.data_array
                        statement_response = query_result_response.get("statement_response", {})
                        if statement_response:
                            # Get columns from manifest
                            manifest = statement_response.get("manifest", {})
                            schema = manifest.get("schema", {})
                            columns = schema.get("columns", [])
                            if columns:
                                result["columns"] = [col.get("name", "") for col in columns]

                            # Get data from result
                            stmt_result = statement_response.get("result", {})
                            if stmt_result:
                                data_array = stmt_result.get("data_array", [])
                                if data_array:
                                    result["data"] = data_array
                                    result["row_count"] = len(data_array)

                        # Fallback: Direct columns/data_array at top level
                        if not result["data"]:
                            columns = query_result_response.get("columns", [])
                            data_array = query_result_response.get("data_array", [])
                            if columns and data_array:
                                result["columns"] = [col.get("name", "") if isinstance(col, dict) else str(col) for col in columns]
                                result["data"] = data_array
                                result["row_count"] = len(data_array)

            if "text" in attachment:
                result["text_response"] = attachment["text"].get("content", "")

            # Some Genie responses include frame with data
            if "frame" in attachment:
                frame = attachment["frame"]
                # Frame might have data
                if "data" in frame and not result["data"]:
                    frame_data = frame["data"]
                    if "columns" in frame_data:
                        result["columns"] = [col.get("name", "") for col in frame_data["columns"]]
                    if "data_array" in frame_data:
                        result["data"] = frame_data["data_array"]
                        result["row_count"] = len(frame_data["data_array"])

        # Check for errors
        if message_response.get("error"):
            result["error"] = message_response.get("error")
            result["status"] = "FAILED"

    except Exception as e:
        result["error"] = str(e)
        result["status"] = "FAILED"

    return result
