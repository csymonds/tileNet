"""
TileNet Session - Per-client session state.

Each connected client gets a Session that tracks:
  - The WebSocket connection
  - The agent objid assigned to this client
  - The set of objids the client has been told about (object cache)
  - The client's current matrix
"""

from __future__ import annotations

import json
import logging
from typing import Any, TYPE_CHECKING

from tilenet.protocol import make_set, make_hear, make_logged_in, make_logged_out, serialize
from tilenet.objects import TileNetObject, Matrix, Token, Agent, Key, ImageObj

if TYPE_CHECKING:
    import websockets

log = logging.getLogger(__name__)


class Session:
    """Represents one connected client's server-side state."""

    def __init__(self, websocket: Any, agent_id: str, server: Any = None):
        self.websocket = websocket
        self.agent_id = agent_id
        self.object_cache: set[str] = set()  # objids the client knows about
        self.current_matrix_id: str | None = None
        self.logged_in: bool = False
        self._server = server  # back-reference for plugins to move agents

    async def send(self, msg: dict[str, Any]) -> None:
        """Send a JSON message to this client."""
        raw = serialize(msg)
        await self.websocket.send(raw)

    async def send_set(self, objid: str, **attrs: Any) -> None:
        """Send a set message and track the objid in the client's cache."""
        msg = make_set(objid, **attrs)
        self.object_cache.add(objid)
        await self.send(msg)

    async def send_hear(self, from_id: str, to_id: str, message: str) -> None:
        """Send a hear message."""
        msg = make_hear(from_id, to_id, message)
        await self.send(msg)

    async def send_logged_in(self, message: str,
                             objid: str | None = None) -> None:
        """Send a logged-in response."""
        msg = make_logged_in(message, objid)
        await self.send(msg)

    async def send_logged_out(self, message: str) -> None:
        """Send a logged-out message."""
        msg = make_logged_out(message)
        await self.send(msg)

    async def send_full_object(self, obj: TileNetObject) -> None:
        """Send a complete object definition as a set message."""
        attrs = obj.to_full_set_attrs()
        await self.send_set(obj.objid, **attrs)

    async def send_matrix_state(self, world: Any, matrix_id: str) -> None:
        """Send the full state of a matrix to this client.

        Order matters per the protocol:
        1. Matrix definition (triggers "Last Is Current")
        2. Images (must be defined before tokens reference them)
        3. Tokens (with positions in the grid)
        4. Keys
        5. Agents (including this client's agent)
        """
        from server.world import World
        assert isinstance(world, World)

        matrix = world.get_matrix(matrix_id)
        if not matrix:
            return

        self.current_matrix_id = matrix_id

        # 1. Send matrix definition
        await self.send_full_object(matrix)

        # 2. Send images
        for img in world.get_images_in_matrix(matrix_id):
            await self.send_full_object(img)

        # 3. Send tokens
        for token in world.get_tokens_in_matrix(matrix_id):
            await self.send_full_object(token)

        # 4. Send keys
        for key in world.get_keys_in_matrix(matrix_id):
            await self.send_full_object(key)

        # 5. Send agents
        for agent in world.get_agents_in_matrix(matrix_id):
            await self.send_full_object(agent)
