import os
import json
import psycopg
import requests
from typing import Optional
from datetime import datetime
from .config import get_workspace_client, get_workspace_host, IS_DATABRICKS_APP

# Import settings
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from settings import ENABLE_HISTORY_PERSISTENCE, LAKEBASE_CONFIG

# Lakebase configuration from settings
LAKEBASE_PROJECT = LAKEBASE_CONFIG["project"]
LAKEBASE_BRANCH = LAKEBASE_CONFIG["branch"]
LAKEBASE_ENDPOINT = f"projects/{LAKEBASE_PROJECT}/branches/{LAKEBASE_BRANCH}/endpoints/primary"
LAKEBASE_HOST = LAKEBASE_CONFIG["host"]
LAKEBASE_DATABASE = LAKEBASE_CONFIG["database"]

# In-memory storage (used when Lakebase is disabled)
_memory_conversations = {}  # {user_email: {key: conversation_data}}
_memory_messages = {}  # {conversation_key: [messages]}


def _get_headers(user_token: Optional[str] = None) -> dict:
    """Get headers for API requests, using user token if available."""
    if user_token:
        return {"Authorization": f"Bearer {user_token}"}
    # Fall back to service principal
    client = get_workspace_client()
    auth_headers = client.config.authenticate()
    return dict(auth_headers) if auth_headers else {}


def get_db_token(user_token: Optional[str] = None) -> str:
    """Generate OAuth token for Lakebase connection using REST API."""
    host = get_workspace_host()
    url = f"{host}/api/2.0/postgres/credentials"
    headers = _get_headers(user_token)
    headers["Content-Type"] = "application/json"
    headers["Accept"] = "application/json"

    response = requests.post(url, headers=headers, json={"endpoint": LAKEBASE_ENDPOINT})
    response.raise_for_status()
    return response.json().get("token", "")


def get_db_user(user_token: Optional[str] = None) -> str:
    """Get database username (current user email)."""
    host = get_workspace_host()
    url = f"{host}/api/2.0/preview/scim/v2/Me"
    headers = _get_headers(user_token)

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json().get("userName", "")


def get_connection(user_token: Optional[str] = None):
    """Get a database connection using user's OAuth token."""
    token = get_db_token(user_token)
    user = get_db_user(user_token)

    conn = psycopg.connect(
        host=LAKEBASE_HOST,
        dbname=LAKEBASE_DATABASE,
        user=user,
        password=token,
        sslmode="require"
    )
    return conn


def init_database(user_token: Optional[str] = None):
    """Initialize database schema."""
    if not ENABLE_HISTORY_PERSISTENCE:
        print("History persistence disabled - using in-memory storage")
        return

    conn = get_connection(user_token)
    try:
        with conn.cursor() as cur:
            # Create conversations table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id SERIAL PRIMARY KEY,
                    key VARCHAR(100) UNIQUE NOT NULL,
                    user_email VARCHAR(255) NOT NULL,
                    genie_conversation_id VARCHAR(100),
                    space_id VARCHAR(100) NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create messages table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id SERIAL PRIMARY KEY,
                    conversation_key VARCHAR(100) NOT NULL REFERENCES conversations(key) ON DELETE CASCADE,
                    message_type VARCHAR(20) NOT NULL,
                    content TEXT,
                    data JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create index for faster queries
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_conversations_user
                ON conversations(user_email)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_conversation
                ON messages(conversation_key)
            """)

            conn.commit()
            print("Database schema initialized successfully")
    except Exception as e:
        print(f"Error initializing database: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def get_user_conversations(user_email: str, user_token: Optional[str] = None) -> list[dict]:
    """Get all conversations for a user."""
    if not ENABLE_HISTORY_PERSISTENCE:
        # Return from memory
        user_convs = _memory_conversations.get(user_email, {})
        return [
            {
                "key": key,
                "genie_conversation_id": conv.get("genie_conversation_id"),
                "space_id": conv.get("space_id"),
                "title": conv.get("title"),
                "created_at": conv.get("created_at"),
                "updated_at": conv.get("updated_at"),
            }
            for key, conv in user_convs.items()
        ]

    conn = get_connection(user_token)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT key, genie_conversation_id, space_id, title, created_at, updated_at
                FROM conversations
                WHERE user_email = %s
                ORDER BY updated_at DESC
            """, (user_email,))

            conversations = []
            for row in cur.fetchall():
                conversations.append({
                    "key": row[0],
                    "genie_conversation_id": row[1],
                    "space_id": row[2],
                    "title": row[3],
                    "created_at": row[4].isoformat() if row[4] else None,
                    "updated_at": row[5].isoformat() if row[5] else None
                })
            return conversations
    finally:
        conn.close()


def create_conversation(user_email: str, key: str, space_id: str, title: str, user_token: Optional[str] = None) -> dict:
    """Create a new conversation."""
    now = datetime.now().isoformat()

    if not ENABLE_HISTORY_PERSISTENCE:
        # Store in memory
        if user_email not in _memory_conversations:
            _memory_conversations[user_email] = {}
        _memory_conversations[user_email][key] = {
            "genie_conversation_id": None,
            "space_id": space_id,
            "title": title,
            "created_at": now,
            "updated_at": now,
        }
        _memory_messages[key] = []
        return {"key": key, "space_id": space_id, "title": title, "created_at": now}

    conn = get_connection(user_token)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO conversations (key, user_email, space_id, title)
                VALUES (%s, %s, %s, %s)
                RETURNING key, space_id, title, created_at
            """, (key, user_email, space_id, title))

            row = cur.fetchone()
            conn.commit()

            return {
                "key": row[0],
                "space_id": row[1],
                "title": row[2],
                "created_at": row[3].isoformat() if row[3] else None
            }
    finally:
        conn.close()


def update_conversation(key: str, genie_conversation_id: str = None, title: str = None, user_token: Optional[str] = None):
    """Update a conversation."""
    if not ENABLE_HISTORY_PERSISTENCE:
        # Update in memory
        for user_convs in _memory_conversations.values():
            if key in user_convs:
                if genie_conversation_id:
                    user_convs[key]["genie_conversation_id"] = genie_conversation_id
                if title:
                    user_convs[key]["title"] = title
                user_convs[key]["updated_at"] = datetime.now().isoformat()
                return
        return

    conn = get_connection(user_token)
    try:
        with conn.cursor() as cur:
            updates = ["updated_at = CURRENT_TIMESTAMP"]
            params = []

            if genie_conversation_id:
                updates.append("genie_conversation_id = %s")
                params.append(genie_conversation_id)

            if title:
                updates.append("title = %s")
                params.append(title)

            params.append(key)

            cur.execute(f"""
                UPDATE conversations
                SET {', '.join(updates)}
                WHERE key = %s
            """, params)

            conn.commit()
    finally:
        conn.close()


def get_conversation(key: str, user_token: Optional[str] = None) -> Optional[dict]:
    """Get a single conversation with its messages."""
    if not ENABLE_HISTORY_PERSISTENCE:
        # Get from memory
        for user_convs in _memory_conversations.values():
            if key in user_convs:
                conv = user_convs[key]
                return {
                    "key": key,
                    "genie_conversation_id": conv.get("genie_conversation_id"),
                    "space_id": conv.get("space_id"),
                    "title": conv.get("title"),
                    "created_at": conv.get("created_at"),
                    "messages": _memory_messages.get(key, [])
                }
        return None

    conn = get_connection(user_token)
    try:
        with conn.cursor() as cur:
            # Get conversation
            cur.execute("""
                SELECT key, genie_conversation_id, space_id, title, created_at
                FROM conversations
                WHERE key = %s
            """, (key,))

            row = cur.fetchone()
            if not row:
                return None

            conversation = {
                "key": row[0],
                "genie_conversation_id": row[1],
                "space_id": row[2],
                "title": row[3],
                "created_at": row[4].isoformat() if row[4] else None,
                "messages": []
            }

            # Get messages
            cur.execute("""
                SELECT message_type, content, data, created_at
                FROM messages
                WHERE conversation_key = %s
                ORDER BY created_at ASC
            """, (key,))

            for msg_row in cur.fetchall():
                conversation["messages"].append({
                    "type": msg_row[0],
                    "content": msg_row[1],
                    "data": msg_row[2],
                    "timestamp": msg_row[3].isoformat() if msg_row[3] else None
                })

            return conversation
    finally:
        conn.close()


def add_message(conversation_key: str, message_type: str, content: str = None, data: dict = None, user_token: Optional[str] = None):
    """Add a message to a conversation."""
    if not ENABLE_HISTORY_PERSISTENCE:
        # Store in memory
        if conversation_key not in _memory_messages:
            _memory_messages[conversation_key] = []
        _memory_messages[conversation_key].append({
            "type": message_type,
            "content": content,
            "data": data,
            "timestamp": datetime.now().isoformat()
        })
        # Update conversation timestamp
        for user_convs in _memory_conversations.values():
            if conversation_key in user_convs:
                user_convs[conversation_key]["updated_at"] = datetime.now().isoformat()
        return

    conn = get_connection(user_token)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO messages (conversation_key, message_type, content, data)
                VALUES (%s, %s, %s, %s)
            """, (conversation_key, message_type, content, json.dumps(data) if data else None))

            # Update conversation timestamp
            cur.execute("""
                UPDATE conversations
                SET updated_at = CURRENT_TIMESTAMP
                WHERE key = %s
            """, (conversation_key,))

            conn.commit()
    finally:
        conn.close()


def delete_conversation(key: str, user_email: str, user_token: Optional[str] = None) -> bool:
    """Delete a conversation (only if owned by user)."""
    if not ENABLE_HISTORY_PERSISTENCE:
        # Delete from memory
        if user_email in _memory_conversations and key in _memory_conversations[user_email]:
            del _memory_conversations[user_email][key]
            if key in _memory_messages:
                del _memory_messages[key]
            return True
        return False

    conn = get_connection(user_token)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM conversations
                WHERE key = %s AND user_email = %s
            """, (key, user_email))

            deleted = cur.rowcount > 0
            conn.commit()
            return deleted
    finally:
        conn.close()
