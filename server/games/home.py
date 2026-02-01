"""
Home Matrix - The lobby/landing page for TileNet.

When players log in, they arrive here. Contains navigation tokens
to enter available games.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from server.game_plugin import GamePlugin

if TYPE_CHECKING:
    from server.world import World
    from server.session import Session

log = logging.getLogger(__name__)


class HomePlugin(GamePlugin):
    """Game plugin for the home/lobby matrix."""

    def __init__(self, world: World, matrix_id: str):
        super().__init__(world, matrix_id)
        self.pp_token_id: str = ""
        # Map of target matrix_id for each navigation token
        self.nav_tokens: dict[str, str] = {}  # token_id -> target matrix_id

    async def initialize(self, sessions: dict[str, Session]) -> None:
        """Set up the home matrix with navigation tokens."""
        matrix = self.world.get_matrix(self.matrix_id)
        if not matrix:
            return

        # Create a "PairPanicking" button token
        pp_token = self.world.create_token(
            name="PairPanicking",
            x=1, y=1,
            energy=1,
            bgcolor="ff2255aa",
            fgcolor="ffffffff",
            text="Click to play PairPanicking!",
        )
        self.world.place_in_matrix(pp_token.objid, self.matrix_id)
        self.pp_token_id = pp_token.objid

        log.info("Home matrix initialized with PP token %s", pp_token.objid)

    def register_nav_token(self, token_id: str, target_matrix_id: str) -> None:
        """Register a navigation token that sends players to a target matrix."""
        self.nav_tokens[token_id] = target_matrix_id

    async def on_agent_enter(self, session: Session, agent_id: str,
                             all_sessions: dict[str, Session]) -> None:
        agent = self.world.get_agent(agent_id)
        if agent:
            # Announce arrival to others in home
            for other in self.world.get_agents_in_matrix(self.matrix_id):
                if other.objid != agent_id:
                    s = all_sessions.get(other.objid)
                    if s:
                        await s.send_hear(
                            self.matrix_id, other.objid,
                            f"{agent.name} has entered the lobby.")

    async def on_agent_leave(self, session: Session, agent_id: str,
                             all_sessions: dict[str, Session]) -> None:
        agent = self.world.get_agent(agent_id)
        if agent:
            for other in self.world.get_agents_in_matrix(self.matrix_id):
                if other.objid != agent_id:
                    s = all_sessions.get(other.objid)
                    if s:
                        await s.send_hear(
                            self.matrix_id, other.objid,
                            f"{agent.name} has left the lobby.")

    async def on_click(self, session: Session, agent_id: str,
                       token_id: str,
                       all_sessions: dict[str, Session]) -> None:
        # Check if it's a navigation token
        target = self.nav_tokens.get(token_id)
        if target:
            # Import here to avoid circular imports
            from server.server import TileNetServer
            # Find the server instance via the session's world
            # We need the server to move agents — use the helper on sessions
            # The server stores itself as an attribute we can access
            log.info("Agent %s navigating to matrix %s", agent_id, target)
            # We need to call server.move_agent_to_matrix
            # The server reference is passed through _server attribute
            if hasattr(session, '_server'):
                await session._server.move_agent_to_matrix(
                    session, agent_id, target)
        else:
            log.debug("Agent %s clicked unknown token %s in home",
                       agent_id, token_id)
