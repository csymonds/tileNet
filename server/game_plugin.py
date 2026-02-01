"""
TileNet Game Plugin - Abstract base class for game logic.

Each game (PairPanicking, Home lobby, etc.) is a plugin attached to a matrix.
The server dispatches client actions to the appropriate plugin.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from server.world import World
    from server.session import Session


class GamePlugin(ABC):
    """Base class for game logic attached to a matrix."""

    def __init__(self, world: World, matrix_id: str):
        self.world = world
        self.matrix_id = matrix_id

    @abstractmethod
    async def initialize(self, sessions: dict[str, Session]) -> None:
        """Called once when the game/matrix is set up.
        Create tokens, images, etc.
        """

    @abstractmethod
    async def on_agent_enter(self, session: Session, agent_id: str,
                             all_sessions: dict[str, Session]) -> None:
        """Called when an agent enters this matrix."""

    @abstractmethod
    async def on_agent_leave(self, session: Session, agent_id: str,
                             all_sessions: dict[str, Session]) -> None:
        """Called when an agent leaves this matrix."""

    @abstractmethod
    async def on_click(self, session: Session, agent_id: str,
                       token_id: str,
                       all_sessions: dict[str, Session]) -> None:
        """Called when an agent clicks a token in this matrix."""

    async def on_say(self, session: Session, agent_id: str,
                     target_id: str, text: str,
                     all_sessions: dict[str, Session]) -> None:
        """Called when an agent says something. Default: broadcast."""
        pass

    async def on_press(self, session: Session, agent_id: str,
                       key_id: str,
                       all_sessions: dict[str, Session]) -> None:
        """Called when an agent presses a bound key. Default: no-op."""
        pass
