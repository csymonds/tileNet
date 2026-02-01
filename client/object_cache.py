"""
TileNet Client Object Cache.

Stores all objects the client has been told about and applies protocol rules:
  - Last Is Current: set on matrix = new current matrix
  - Current Is Container: set on token/agent/key = in current matrix
  - X To Exit: set with x < 0 = object left current matrix
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

# Object type characters
_MATRIX = "m"
_AGENT = "a"
_TOKEN = "t"
_KEY = "k"
_IMAGE = "i"
_CONTAINED_TYPES = {_AGENT, _TOKEN, _KEY}


class ObjectCache:
    """Client-side object cache implementing TileNet protocol semantics."""

    def __init__(self):
        # objid -> dict of attributes (including _type, _container)
        self.objects: dict[str, dict[str, Any]] = {}
        self.current_matrix_id: str | None = None
        self.my_agent_id: str | None = None

    def process_set(self, msg: dict[str, Any]) -> tuple[str, bool]:
        """Apply a set message to the cache.

        Returns:
            (objid, matrix_changed) — True if the current matrix changed.
        """
        objid = msg.get("objid", "")
        if not objid:
            return "", False

        obj_type = objid[0]

        # Get or create object
        if objid not in self.objects:
            self.objects[objid] = {"objid": objid, "_type": obj_type}
        obj = self.objects[objid]

        matrix_changed = False

        # LAST IS CURRENT: matrix set = new current matrix
        if obj_type == _MATRIX:
            old_matrix = self.current_matrix_id
            self.current_matrix_id = objid
            if old_matrix != objid:
                matrix_changed = True

        # X TO EXIT: negative x on contained type = left current matrix
        x_val = msg.get("x")
        if obj_type in _CONTAINED_TYPES and x_val is not None and x_val < 0:
            obj["_container"] = None
        elif obj_type in _CONTAINED_TYPES:
            # CURRENT IS CONTAINER: object is in the current matrix
            obj["_container"] = self.current_matrix_id

        # Update all provided attributes
        for key in ("name", "text", "energy", "bgcolor", "fgcolor",
                    "x", "y", "image"):
            if key in msg:
                obj[key] = msg[key]

        return objid, matrix_changed

    def get_object(self, objid: str) -> dict[str, Any] | None:
        return self.objects.get(objid)

    def get_current_matrix(self) -> dict[str, Any] | None:
        if self.current_matrix_id:
            return self.objects.get(self.current_matrix_id)
        return None

    def get_matrix_tokens(self) -> list[dict[str, Any]]:
        """Return all tokens currently in the current matrix, sorted by (y, x)."""
        if not self.current_matrix_id:
            return []
        tokens = [
            o for o in self.objects.values()
            if o.get("_type") == _TOKEN
            and o.get("_container") == self.current_matrix_id
            and o.get("x", 0) >= 0  # not exited
        ]
        tokens.sort(key=lambda t: (t.get("y", 0), t.get("x", 0)))
        return tokens

    def get_matrix_agents(self) -> list[dict[str, Any]]:
        """Return all agents currently in the current matrix."""
        if not self.current_matrix_id:
            return []
        return [
            o for o in self.objects.values()
            if o.get("_type") == _AGENT
            and o.get("_container") == self.current_matrix_id
            and o.get("x", 0) >= 0
        ]

    def get_my_agent(self) -> dict[str, Any] | None:
        if self.my_agent_id:
            return self.objects.get(self.my_agent_id)
        return None

    def get_image_data(self, image_objid: str) -> str | None:
        """Return the hex-encoded image data for an image objid, or None."""
        obj = self.objects.get(image_objid)
        if obj and obj.get("_type") == _IMAGE:
            return obj.get("text")
        return None
