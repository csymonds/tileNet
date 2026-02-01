"""
TileNet Protocol - JSON message builders and utilities.

Modernized from the original TileNet 1.0 XML/TCP protocol to JSON/WebSocket.
Preserves the same message types and semantics:
  Server -> Client: server, logged-in, set, hear, logged-out
  Client -> Server: login, cmd, logout
"""

from __future__ import annotations

import json
from typing import Any

# Protocol version
VERSION = "1.0"

# Object type prefixes
OBJ_MATRIX = "m"
OBJ_AGENT = "a"
OBJ_TOKEN = "t"
OBJ_KEY = "k"
OBJ_IMAGE = "i"

VALID_OBJ_TYPES = {OBJ_MATRIX, OBJ_AGENT, OBJ_TOKEN, OBJ_KEY, OBJ_IMAGE}

# Command types
CMD_CLICK = "click"
CMD_SAY = "say"
CMD_PRESS = "press"

# Server status values
STATUS_OPEN = "open"
STATUS_CLOSED = "closed"
STATUS_BUSY = "busy"


def parse_objid(objid: str) -> tuple[str, int]:
    """Parse an objid like 'm3' into (type_char, id_number).

    Returns:
        Tuple of (type_char, numeric_id).

    Raises:
        ValueError: If objid format is invalid.
    """
    if not objid or len(objid) < 2:
        raise ValueError(f"Invalid objid: {objid!r}")
    type_char = objid[0]
    if type_char not in VALID_OBJ_TYPES:
        raise ValueError(f"Unknown object type in objid: {objid!r}")
    try:
        num = int(objid[1:])
    except ValueError:
        raise ValueError(f"Non-numeric id in objid: {objid!r}")
    return type_char, num


def obj_type(objid: str) -> str:
    """Return the type character of an objid (e.g., 'm' for 'm3')."""
    return objid[0] if objid else ""


# ---------------------------------------------------------------------------
# Server -> Client message builders
# ---------------------------------------------------------------------------

def make_server_hello(group: str, name: str, status: str) -> dict[str, Any]:
    """Server hello message, sent immediately on connection."""
    return {
        "type": "server",
        "version": VERSION,
        "group": group,
        "name": name,
        "status": status,
    }


def make_logged_in(message: str, objid: str | None = None) -> dict[str, Any]:
    """Login response. Include objid for success, omit for failure."""
    msg: dict[str, Any] = {"type": "logged-in", "message": message}
    if objid is not None:
        msg["objid"] = objid
    return msg


def make_set(objid: str, **attrs: Any) -> dict[str, Any]:
    """Build a set message. Only include attributes that are provided.

    Valid attrs: name, text, energy, bgcolor, fgcolor, x, y, image
    """
    msg: dict[str, Any] = {"type": "set", "objid": objid}
    for key in ("name", "text", "energy", "bgcolor", "fgcolor", "x", "y", "image"):
        if key in attrs:
            msg[key] = attrs[key]
    return msg


def make_hear(from_id: str, to_id: str, message: str) -> dict[str, Any]:
    """Chat/speech message from server to client."""
    return {
        "type": "hear",
        "from": from_id,
        "to": to_id,
        "message": message,
    }


def make_logged_out(message: str) -> dict[str, Any]:
    """Server informs client the session is ending."""
    return {"type": "logged-out", "message": message}


# ---------------------------------------------------------------------------
# Client -> Server message builders
# ---------------------------------------------------------------------------

def make_login(user: str, password: str) -> dict[str, Any]:
    """Client login request."""
    return {"type": "login", "user": user, "password": password}


def make_cmd(cmd_type: str, objid: str, text: str | None = None) -> dict[str, Any]:
    """Client command: click, say, or press."""
    msg: dict[str, Any] = {"type": "cmd", "cmd_type": cmd_type, "objid": objid}
    if text is not None:
        msg["text"] = text
    return msg


def make_logout(message: str = "") -> dict[str, Any]:
    """Client logout request."""
    return {"type": "logout", "message": message}


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def serialize(msg: dict[str, Any]) -> str:
    """Serialize a message dict to a JSON string."""
    return json.dumps(msg, separators=(",", ":"))


def deserialize(data: str) -> dict[str, Any]:
    """Deserialize a JSON string to a message dict."""
    return json.loads(data)
