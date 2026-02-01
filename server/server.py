"""
TileNet Server - WebSocket server, connection management, session lifecycle.

Handles:
  - Accepting WebSocket connections
  - Server hello handshake
  - Login authentication
  - Dispatching commands to the World and GamePlugins
  - Agent lifecycle (creation, matrix placement, cleanup on disconnect)
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import websockets
from websockets.asyncio.server import serve, ServerConnection

from tilenet.protocol import (
    make_server_hello, make_hear, serialize, deserialize,
    STATUS_OPEN, STATUS_BUSY, CMD_CLICK, CMD_SAY, CMD_PRESS,
    obj_type, OBJ_AGENT, OBJ_TOKEN,
)
from tilenet.objects import Agent
from server.world import World
from server.session import Session

log = logging.getLogger(__name__)


class TileNetServer:
    """The main TileNet WebSocket server."""

    def __init__(self, world: World, host: str = "0.0.0.0", port: int = 44455,
                 group: str = "tileNet", name: str = "TileNet Python Server",
                 max_clients: int = 50):
        self.world = world
        self.host = host
        self.port = port
        self.group = group
        self.name = name
        self.max_clients = max_clients
        # agent_id -> Session
        self.sessions: dict[str, Session] = {}
        self.home_matrix_id: str = ""

    async def start(self) -> None:
        """Start listening for connections. Stops cleanly on cancellation."""
        log.info("TileNet server starting on %s:%d", self.host, self.port)
        self._stop_event = asyncio.Event()
        async with serve(self.handle_client, self.host, self.port):
            # Poll with short sleeps so that Windows signal handlers
            # (which need the main thread to wake up) get a chance to fire.
            while not self._stop_event.is_set():
                await asyncio.sleep(0.5)
        log.info("TileNet server stopped")

    def shutdown(self) -> None:
        """Signal the server to stop accepting connections."""
        if hasattr(self, '_stop_event'):
            self._stop_event.set()

    async def handle_client(self, websocket: ServerConnection) -> None:
        """Handle one client connection through its full lifecycle."""
        session: Session | None = None
        agent_id: str | None = None

        try:
            # 1. Send server hello
            status = STATUS_OPEN if len(self.sessions) < self.max_clients else STATUS_BUSY
            hello = make_server_hello(self.group, self.name, status)
            await websocket.send(serialize(hello))

            if status == STATUS_BUSY:
                log.info("Rejected connection (server busy)")
                return

            # 2. Login loop
            agent_id, session = await self._handle_login(websocket)
            if not session:
                return

            # 3. Place agent in home matrix
            await self._place_agent_in_matrix(session, agent_id,
                                              self.home_matrix_id)

            # 4. Command loop
            async for raw in websocket:
                try:
                    msg = deserialize(raw)
                except json.JSONDecodeError:
                    log.warning("Invalid JSON from %s", agent_id)
                    continue

                msg_type = msg.get("type")
                if msg_type == "cmd":
                    await self._handle_cmd(session, agent_id, msg)
                elif msg_type == "logout":
                    log.info("Agent %s logging out", agent_id)
                    break
                else:
                    log.warning("Unexpected message type %r from %s",
                                msg_type, agent_id)

        except websockets.ConnectionClosed:
            log.info("Connection closed for agent %s", agent_id or "unknown")
        except Exception:
            log.exception("Error handling client %s", agent_id or "unknown")
        finally:
            # Cleanup
            if agent_id and session:
                await self._remove_agent(session, agent_id)

    async def _handle_login(self, websocket: ServerConnection
                            ) -> tuple[str | None, Session | None]:
        """Handle the login handshake. Returns (agent_id, session) or (None, None)."""
        attempts = 0
        max_attempts = 5

        while attempts < max_attempts:
            try:
                raw = await asyncio.wait_for(websocket.recv(), timeout=300.0)
            except asyncio.TimeoutError:
                log.warning("Login timeout")
                return None, None
            except websockets.ConnectionClosed:
                return None, None

            try:
                msg = deserialize(raw)
            except json.JSONDecodeError:
                log.warning("Invalid JSON during login")
                return None, None

            if msg.get("type") != "login":
                log.warning("Expected login, got %r", msg.get("type"))
                return None, None

            user = msg.get("user", "").strip()
            password = msg.get("password", "")

            # Validate username
            if not user or "<" in user:
                session_temp = Session(websocket, "")
                await session_temp.send_logged_in(
                    "Invalid username. Must be non-empty and contain no '<'.")
                attempts += 1
                continue

            # Check for duplicate username
            for s in self.sessions.values():
                agent = self.world.get_agent(s.agent_id)
                if agent and agent.name == user:
                    session_temp = Session(websocket, "")
                    await session_temp.send_logged_in(
                        f"Username '{user}' is already in use.")
                    attempts += 1
                    break
            else:
                # Create agent
                remote_addr = str(websocket.remote_address) if websocket.remote_address else "unknown"
                agent = self.world.create_agent(name=user, text=remote_addr,
                                                energy=10)
                session = Session(websocket, agent.objid, server=self)
                session.logged_in = True
                self.sessions[agent.objid] = session

                await session.send_logged_in(
                    f"Welcome to {self.name}, {user}!", objid=agent.objid)
                log.info("Agent %s (%s) logged in from %s",
                         agent.objid, user, remote_addr)
                return agent.objid, session

        log.warning("Too many login attempts")
        return None, None

    async def _place_agent_in_matrix(self, session: Session,
                                     agent_id: str,
                                     matrix_id: str) -> None:
        """Place an agent into a matrix and notify all relevant clients."""
        agent = self.world.get_agent(agent_id)
        if not agent:
            return

        # Remove from old matrix if any
        old_matrix = agent.container_matrix
        if old_matrix:
            self.world.remove_from_matrix(agent_id)
            # Notify agents in old matrix that this agent left (X To Exit)
            for other_agent in self.world.get_agents_in_matrix(old_matrix):
                other_session = self.sessions.get(other_agent.objid)
                if other_session:
                    await other_session.send_set(agent_id, x=-1)

            # Notify game plugin
            plugin = self.world.get_plugin(old_matrix)
            if plugin:
                await plugin.on_agent_leave(session, agent_id, self.sessions)

        # Place in new matrix
        self.world.place_in_matrix(agent_id, matrix_id)

        # Send full matrix state to the moving agent
        await session.send_matrix_state(self.world, matrix_id)

        # Notify agents already in the new matrix about the new arrival
        for other_agent in self.world.get_agents_in_matrix(matrix_id):
            if other_agent.objid != agent_id:
                other_session = self.sessions.get(other_agent.objid)
                if other_session:
                    await other_session.send_full_object(agent)

        # Notify game plugin
        plugin = self.world.get_plugin(matrix_id)
        if plugin:
            await plugin.on_agent_enter(session, agent_id, self.sessions)

    async def _handle_cmd(self, session: Session, agent_id: str,
                          msg: dict[str, Any]) -> None:
        """Dispatch a client command to the appropriate handler."""
        cmd_type = msg.get("cmd_type")
        objid = msg.get("objid", "")

        agent = self.world.get_agent(agent_id)
        if not agent:
            return

        matrix_id = agent.container_matrix
        if not matrix_id:
            return

        if cmd_type == CMD_CLICK:
            await self._handle_click(session, agent_id, objid, matrix_id)
        elif cmd_type == CMD_SAY:
            text = msg.get("text", "")
            await self._handle_say(session, agent_id, objid, text, matrix_id)
        elif cmd_type == CMD_PRESS:
            await self._handle_press(session, agent_id, objid, matrix_id)
        else:
            log.warning("Unknown cmd_type %r from %s", cmd_type, agent_id)

    async def _handle_click(self, session: Session, agent_id: str,
                            token_id: str, matrix_id: str) -> None:
        """Handle a click command."""
        # Validate: must be a token type
        if not token_id or obj_type(token_id) != OBJ_TOKEN:
            log.warning("Illegal click target %r from %s", token_id, agent_id)
            return

        # Check token exists and is in same matrix
        token = self.world.get_token(token_id)
        if not token or token.container_matrix != matrix_id:
            return  # not executable

        # Check token energy
        if token.energy <= 0:
            return  # disabled token

        # Dispatch to game plugin (plugin handles agent energy checks
        # so that control tokens like Home/Restart remain clickable
        # even when the agent's energy is depleted)
        plugin = self.world.get_plugin(matrix_id)
        if plugin:
            await plugin.on_click(session, agent_id, token_id, self.sessions)

    async def _handle_say(self, session: Session, agent_id: str,
                          target_id: str, text: str,
                          matrix_id: str) -> None:
        """Handle a say command."""
        text = text.strip()
        if not text:
            return

        # If target is an agent, use the chat broadcast / whisper rules
        if obj_type(target_id) == OBJ_AGENT:
            is_whisper = text.startswith("(") and text.endswith(")")

            if is_whisper:
                # Send only to the target agent
                target_session = self.sessions.get(target_id)
                if target_session:
                    await target_session.send_hear(agent_id, target_id, text)
            else:
                # Broadcast to all agents in the same matrix as target
                target_agent = self.world.get_agent(target_id)
                target_matrix = target_agent.container_matrix if target_agent else matrix_id
                for a in self.world.get_agents_in_matrix(target_matrix):
                    s = self.sessions.get(a.objid)
                    if s:
                        await s.send_hear(agent_id, target_id, text)
        else:
            # Non-agent target: dispatch to plugin
            plugin = self.world.get_plugin(matrix_id)
            if plugin:
                await plugin.on_say(session, agent_id, target_id, text,
                                    self.sessions)

    async def _handle_press(self, session: Session, agent_id: str,
                            key_id: str, matrix_id: str) -> None:
        """Handle a key press command."""
        agent = self.world.get_agent(agent_id)
        if agent and agent.energy <= 0:
            return

        plugin = self.world.get_plugin(matrix_id)
        if plugin:
            await plugin.on_press(session, agent_id, key_id, self.sessions)

    async def _remove_agent(self, session: Session, agent_id: str) -> None:
        """Clean up when an agent disconnects."""
        agent = self.world.get_agent(agent_id)
        if not agent:
            return

        matrix_id = agent.container_matrix

        # Notify plugin
        if matrix_id:
            plugin = self.world.get_plugin(matrix_id)
            if plugin:
                await plugin.on_agent_leave(session, agent_id, self.sessions)

        # Remove from matrix, notify peers
        if matrix_id:
            self.world.remove_from_matrix(agent_id)
            for other_agent in self.world.get_agents_in_matrix(matrix_id):
                other_session = self.sessions.get(other_agent.objid)
                if other_session:
                    try:
                        await other_session.send_set(agent_id, x=-1)
                    except Exception:
                        pass

        # Send logged-out if possible
        try:
            await session.send_logged_out("Goodbye!")
        except Exception:
            pass

        # Remove from sessions
        self.sessions.pop(agent_id, None)
        log.info("Agent %s removed", agent_id)

    # ------------------------------------------------------------------
    # Public helper for plugins to move agents between matrices
    # ------------------------------------------------------------------

    async def move_agent_to_matrix(self, session: Session,
                                   agent_id: str,
                                   target_matrix_id: str) -> None:
        """Move an agent to a different matrix. Used by game plugins."""
        await self._place_agent_in_matrix(session, agent_id,
                                          target_matrix_id)
