"""
PairPanicking - A multiplayer real-time memory/concentration game.

Game Rules (from the spec):
  - 8x8 grid, 16 symbols x 4 copies = 64 squares
  - Squares are hidden, showing, or solved
  - Click hidden -> reveal. At most 2 showing at once.
  - 2nd reveal starts a 2-second timer
  - Match -> solved, Mismatch -> re-hidden
  - 3rd click cancels timer, resolves, then processes new click
  - Scoring: match +2 all / +4 trigger, mismatch -1 active / -1 trigger
  - Game over when 0 active players or 64 solved

Matrix layout: 9 cols x 8 rows
  Cols 0-7: game grid (8x8)
  Col 8: control tokens (Home, Help, Restart)
"""

from __future__ import annotations

import asyncio
import logging
import random
from pathlib import Path
from typing import TYPE_CHECKING

from server.game_plugin import GamePlugin
from tilenet.objects import Token, ImageObj

if TYPE_CHECKING:
    from server.world import World
    from server.session import Session

log = logging.getLogger(__name__)

# The 16 symbol names, matching the image files in images/
SYMBOLS = [
    "beer", "duck", "fairy", "flowers", "hobbiton", "hydrant",
    "lady", "panda", "robot", "rose", "saturn", "skull",
    "tardis", "toilet", "turtle", "woman",
]

GRID_ROWS = 8
GRID_COLS = 8
TOTAL_SQUARES = 64
COPIES_PER_SYMBOL = 4
REVEAL_TIMEOUT = 2.0  # seconds

HIDDEN_NAME = "???"
SOLVED_NAME = ""

START_ENERGY = 10

# Colors (RGBA hex)
HIDDEN_BGCOLOR = "ff334455"
HIDDEN_FGCOLOR = "ffaabbcc"
SHOWING_BGCOLOR = "ff225588"
SHOWING_FGCOLOR = "ffffffff"
SOLVED_BGCOLOR = "33222222"
SOLVED_FGCOLOR = "33666666"
CONTROL_BGCOLOR = "ff11aa44"
CONTROL_FGCOLOR = "ffffffff"
HOME_BGCOLOR = "ffcc6600"
HOME_FGCOLOR = "ffffffff"


class PairPanickingPlugin(GamePlugin):
    """Server-side game logic for PairPanicking."""

    def __init__(self, world: World, matrix_id: str):
        super().__init__(world, matrix_id)

        # Grid state: [row][col] -> symbol name
        self.board: list[list[str]] = []
        # Grid state: [row][col] -> "hidden" / "showing" / "solved"
        self.state: list[list[str]] = []
        # Grid token objids: [row][col] -> token objid
        self.token_grid: list[list[str]] = []
        # Reverse lookup: token_id -> (row, col)
        self.token_positions: dict[str, tuple[int, int]] = {}

        # Currently showing squares (max 2)
        self.showing: list[tuple[int, int]] = []
        self.trigger_agent: str | None = None  # who revealed the 2nd square
        self.timer_task: asyncio.Task | None = None

        # Scoring
        self.scores: dict[str, int] = {}  # agent_id -> score
        self.game_in_progress: bool = False
        self.solved_count: int = 0

        # Control token objids
        self.home_token_id: str = ""
        self.help_token_id: str = ""
        self.restart_token_id: str = ""

        # Image objids: symbol_name -> image objid
        self.symbol_images: dict[str, str] = {}
        self.hidden_image_id: str = ""

    async def initialize(self, sessions: dict[str, Session]) -> None:
        """Create all tokens, load images, set up the board."""
        await self._load_images()
        self._create_grid_tokens()
        self._create_control_tokens()
        self._setup_new_game()

    async def _load_images(self) -> None:
        """Load the 16 symbol JPEGs and create image objects."""
        images_dir = Path(__file__).resolve().parent / "images"

        for symbol in SYMBOLS:
            img_path = images_dir / f"{symbol}.jpg"
            if img_path.exists():
                hex_data = img_path.read_bytes().hex()
                img_obj = self.world.create_image(
                    hex_data=hex_data, width=64, height=64)
                self.symbol_images[symbol] = img_obj.objid
                self.world.place_in_matrix(img_obj.objid, self.matrix_id)
            else:
                log.warning("Image not found: %s", img_path)

        # Create the "hidden" image (a question mark placeholder)
        # We'll use a simple approach: no image for hidden, just the "???" text
        self.hidden_image_id = ""

        log.info("Loaded %d symbol images for PairPanicking",
                 len(self.symbol_images))

    def _create_grid_tokens(self) -> None:
        """Create the 64 grid tokens (8x8)."""
        self.token_grid = []
        self.token_positions = {}

        for row in range(GRID_ROWS):
            row_tokens = []
            for col in range(GRID_COLS):
                token = self.world.create_token(
                    name=HIDDEN_NAME,
                    x=col, y=row,
                    energy=1,
                    bgcolor=HIDDEN_BGCOLOR,
                    fgcolor=HIDDEN_FGCOLOR,
                )
                self.world.place_in_matrix(token.objid, self.matrix_id)
                row_tokens.append(token.objid)
                self.token_positions[token.objid] = (row, col)
            self.token_grid.append(row_tokens)

    def _create_control_tokens(self) -> None:
        """Create Home, Help, and Restart control tokens in column 8."""
        # Home button — bright orange so it stands out
        home = self.world.create_token(
            name="< Home", x=8, y=0, energy=1,
            bgcolor=HOME_BGCOLOR, fgcolor=HOME_FGCOLOR,
            text="Return to lobby",
        )
        self.world.place_in_matrix(home.objid, self.matrix_id)
        self.home_token_id = home.objid

        # Help button
        help_tok = self.world.create_token(
            name="? Help", x=8, y=2, energy=1,
            bgcolor=CONTROL_BGCOLOR, fgcolor=CONTROL_FGCOLOR,
            text="Click for instructions",
        )
        self.world.place_in_matrix(help_tok.objid, self.matrix_id)
        self.help_token_id = help_tok.objid

        # Restart button
        restart = self.world.create_token(
            name="New Game", x=8, y=4, energy=1,
            bgcolor=CONTROL_BGCOLOR, fgcolor=CONTROL_FGCOLOR,
            text="Start a new game",
        )
        self.world.place_in_matrix(restart.objid, self.matrix_id)
        self.restart_token_id = restart.objid

    def _setup_new_game(self) -> None:
        """Shuffle symbols and reset board state."""
        # Build symbol list: 16 symbols x 4 copies = 64
        symbols = SYMBOLS * COPIES_PER_SYMBOL
        random.shuffle(symbols)

        self.board = []
        self.state = []
        idx = 0
        for row in range(GRID_ROWS):
            board_row = []
            state_row = []
            for col in range(GRID_COLS):
                board_row.append(symbols[idx])
                state_row.append("hidden")
                idx += 1
            self.board.append(board_row)
            self.state.append(state_row)

        self.showing = []
        self.trigger_agent = None
        self.solved_count = 0
        self.game_in_progress = True

        if self.timer_task and not self.timer_task.done():
            self.timer_task.cancel()
            self.timer_task = None

    async def _reset_game(self, all_sessions: dict[str, Session]) -> None:
        """Reset the board and update all clients."""
        self._setup_new_game()

        # Reset all grid tokens to hidden
        for row in range(GRID_ROWS):
            for col in range(GRID_COLS):
                token_id = self.token_grid[row][col]
                token = self.world.get_token(token_id)
                if token:
                    token.name = HIDDEN_NAME
                    token.bgcolor = HIDDEN_BGCOLOR
                    token.fgcolor = HIDDEN_FGCOLOR
                    token.energy = 1
                    token.image = self.hidden_image_id

                # Notify all clients in the matrix
                await self._broadcast_set(
                    all_sessions, token_id,
                    name=HIDDEN_NAME,
                    bgcolor=HIDDEN_BGCOLOR,
                    fgcolor=HIDDEN_FGCOLOR,
                    energy=1,
                    image=self.hidden_image_id,
                )

        # Reset scores for all agents in matrix
        for agent_id in list(self.scores.keys()):
            self.scores[agent_id] = START_ENERGY
            agent = self.world.get_agent(agent_id)
            if agent:
                agent.energy = START_ENERGY
            await self._broadcast_set(
                all_sessions, agent_id, energy=START_ENERGY)

        # Disable restart button during game
        restart = self.world.get_token(self.restart_token_id)
        if restart:
            restart.energy = -1
        await self._broadcast_set(
            all_sessions, self.restart_token_id, energy=-1)

    # ------------------------------------------------------------------
    # Plugin hooks
    # ------------------------------------------------------------------

    async def on_agent_enter(self, session: Session, agent_id: str,
                             all_sessions: dict[str, Session]) -> None:
        """New agent enters PairPanicking."""
        # Set starting score (minus 1 for entering per spec rule 7.1)
        score = START_ENERGY - 1
        self.scores[agent_id] = score

        agent = self.world.get_agent(agent_id)
        if agent:
            agent.energy = score

        # Notify the entering agent of their energy
        await session.send_set(agent_id, energy=score)

        # Announce to all
        agent_name = agent.name if agent else agent_id
        await self._broadcast_hear(
            all_sessions, self.matrix_id, self.matrix_id,
            f"{agent_name} joined PairPanicking! (Score: {score})")

        # If no game in progress, enable restart
        if not self.game_in_progress:
            restart = self.world.get_token(self.restart_token_id)
            if restart:
                restart.energy = 1
            await self._broadcast_set(
                all_sessions, self.restart_token_id, energy=1)

    async def on_agent_leave(self, session: Session, agent_id: str,
                             all_sessions: dict[str, Session]) -> None:
        """Agent leaves PairPanicking."""
        self.scores.pop(agent_id, None)

        agent = self.world.get_agent(agent_id)
        agent_name = agent.name if agent else agent_id

        await self._broadcast_hear(
            all_sessions, self.matrix_id, self.matrix_id,
            f"{agent_name} left PairPanicking.")

        # Check if game over (no active players left)
        if self.game_in_progress:
            active = [aid for aid, s in self.scores.items() if s > 0]
            if not active:
                await self._game_over(all_sessions, has_winner=False)

    async def on_click(self, session: Session, agent_id: str,
                       token_id: str,
                       all_sessions: dict[str, Session]) -> None:
        """Handle a click on a token."""
        # Control tokens
        if token_id == self.home_token_id:
            await self._handle_home(session, agent_id, all_sessions)
            return
        if token_id == self.help_token_id:
            await self._handle_help(session, agent_id)
            return
        if token_id == self.restart_token_id:
            await self._handle_restart(session, agent_id, all_sessions)
            return

        # Game grid click
        pos = self.token_positions.get(token_id)
        if not pos:
            return
        row, col = pos

        if not self.game_in_progress:
            return

        # Check agent is active
        agent_score = self.scores.get(agent_id, 0)
        if agent_score <= 0:
            return

        # Only hidden squares can be clicked
        if self.state[row][col] != "hidden":
            return

        # If we have 2 showing and timer is running, 3rd click ends timer early
        if len(self.showing) >= 2:
            await self._resolve(all_sessions)

        # Reveal this square
        self.state[row][col] = "showing"
        self.showing.append((row, col))
        symbol = self.board[row][col]
        image_id = self.symbol_images.get(symbol, "")

        token = self.world.get_token(token_id)
        if token:
            token.name = symbol
            token.bgcolor = SHOWING_BGCOLOR
            token.fgcolor = SHOWING_FGCOLOR
            token.image = image_id

        await self._broadcast_set(
            all_sessions, token_id,
            name=symbol,
            bgcolor=SHOWING_BGCOLOR,
            fgcolor=SHOWING_FGCOLOR,
            image=image_id,
        )

        # If this is the 2nd reveal, start the timer
        if len(self.showing) == 2:
            self.trigger_agent = agent_id
            self.timer_task = asyncio.create_task(
                self._timer_coro(all_sessions))

    async def _timer_coro(self, all_sessions: dict[str, Session]) -> None:
        """2-second timer. On expiry, resolve the two showing squares."""
        try:
            await asyncio.sleep(REVEAL_TIMEOUT)
            await self._resolve(all_sessions)
        except asyncio.CancelledError:
            pass  # Timer was cancelled by a 3rd click

    async def _resolve(self, all_sessions: dict[str, Session]) -> None:
        """Resolve the two currently showing squares."""
        # Cancel timer if running
        if self.timer_task and not self.timer_task.done():
            self.timer_task.cancel()
            self.timer_task = None

        if len(self.showing) < 2:
            return

        r1, c1 = self.showing[0]
        r2, c2 = self.showing[1]
        self.showing.clear()

        sym1 = self.board[r1][c1]
        sym2 = self.board[r2][c2]

        if sym1 == sym2:
            # Match!
            await self._handle_match(r1, c1, r2, c2, all_sessions)
        else:
            # Mismatch
            await self._handle_mismatch(r1, c1, r2, c2, all_sessions)

    async def _handle_match(self, r1: int, c1: int, r2: int, c2: int,
                            all_sessions: dict[str, Session]) -> None:
        """Two squares matched — mark as solved, award points."""
        # Mark solved
        for r, c in [(r1, c1), (r2, c2)]:
            self.state[r][c] = "solved"
            self.solved_count += 1
            token_id = self.token_grid[r][c]
            token = self.world.get_token(token_id)
            if token:
                token.name = SOLVED_NAME
                token.bgcolor = SOLVED_BGCOLOR
                token.fgcolor = SOLVED_FGCOLOR
                token.energy = 0  # disabled
                token.image = ""

            await self._broadcast_set(
                all_sessions, token_id,
                name=SOLVED_NAME,
                bgcolor=SOLVED_BGCOLOR,
                fgcolor=SOLVED_FGCOLOR,
                energy=0,
                image="",
            )

        # Award points: +2 all, +4 additional for trigger
        for agent_id in list(self.scores.keys()):
            bonus = 4 if agent_id == self.trigger_agent else 0
            self.scores[agent_id] = self.scores[agent_id] + 2 + bonus
            agent = self.world.get_agent(agent_id)
            if agent:
                agent.energy = self.scores[agent_id]
            await self._broadcast_set(
                all_sessions, agent_id, energy=self.scores[agent_id])

        trigger_name = ""
        if self.trigger_agent:
            a = self.world.get_agent(self.trigger_agent)
            trigger_name = a.name if a else self.trigger_agent

        await self._broadcast_hear(
            all_sessions, self.matrix_id, self.matrix_id,
            f"{trigger_name} found a match!")

        # Check win condition
        if self.solved_count >= TOTAL_SQUARES:
            await self._game_over(all_sessions, has_winner=True)

    async def _handle_mismatch(self, r1: int, c1: int, r2: int, c2: int,
                                all_sessions: dict[str, Session]) -> None:
        """Two squares didn't match — re-hide them, deduct points."""
        for r, c in [(r1, c1), (r2, c2)]:
            self.state[r][c] = "hidden"
            token_id = self.token_grid[r][c]
            token = self.world.get_token(token_id)
            if token:
                token.name = HIDDEN_NAME
                token.bgcolor = HIDDEN_BGCOLOR
                token.fgcolor = HIDDEN_FGCOLOR
                token.image = self.hidden_image_id

            await self._broadcast_set(
                all_sessions, token_id,
                name=HIDDEN_NAME,
                bgcolor=HIDDEN_BGCOLOR,
                fgcolor=HIDDEN_FGCOLOR,
                image=self.hidden_image_id,
            )

        # Deduct points: -1 all active, -1 additional for trigger
        newly_inactive = []
        for agent_id in list(self.scores.keys()):
            if self.scores[agent_id] <= 0:
                continue  # already inactive
            penalty = 2 if agent_id == self.trigger_agent else 1
            self.scores[agent_id] = self.scores[agent_id] - penalty
            agent = self.world.get_agent(agent_id)
            if agent:
                agent.energy = self.scores[agent_id]
            await self._broadcast_set(
                all_sessions, agent_id, energy=self.scores[agent_id])

            if self.scores[agent_id] <= 0:
                newly_inactive.append(agent_id)

        for agent_id in newly_inactive:
            a = self.world.get_agent(agent_id)
            name = a.name if a else agent_id
            await self._broadcast_hear(
                all_sessions, self.matrix_id, self.matrix_id,
                f"{name} has been eliminated!")

        # Check if all active players eliminated
        active = [aid for aid, s in self.scores.items() if s > 0]
        if not active and self.game_in_progress:
            await self._game_over(all_sessions, has_winner=False)

    async def _game_over(self, all_sessions: dict[str, Session],
                         has_winner: bool) -> None:
        """End the game."""
        self.game_in_progress = False

        if has_winner:
            # Find winner (highest score)
            winner_id = max(self.scores, key=self.scores.get, default=None)
            if winner_id:
                a = self.world.get_agent(winner_id)
                name = a.name if a else winner_id
                await self._broadcast_hear(
                    all_sessions, self.matrix_id, self.matrix_id,
                    f"Game Over! {name} wins with {self.scores[winner_id]} points!")
            else:
                await self._broadcast_hear(
                    all_sessions, self.matrix_id, self.matrix_id,
                    "Game Over!")
        else:
            await self._broadcast_hear(
                all_sessions, self.matrix_id, self.matrix_id,
                "Game Over! No active players remain.")

            # Reveal all squares
            await self._reveal_all(all_sessions)

        # Enable restart button
        restart = self.world.get_token(self.restart_token_id)
        if restart:
            restart.energy = 1
        await self._broadcast_set(
            all_sessions, self.restart_token_id, energy=1)

    async def _reveal_all(self, all_sessions: dict[str, Session]) -> None:
        """Reveal all hidden squares (for game over display)."""
        for row in range(GRID_ROWS):
            for col in range(GRID_COLS):
                if self.state[row][col] == "hidden":
                    token_id = self.token_grid[row][col]
                    symbol = self.board[row][col]
                    image_id = self.symbol_images.get(symbol, "")

                    token = self.world.get_token(token_id)
                    if token:
                        token.name = symbol
                        token.image = image_id

                    await self._broadcast_set(
                        all_sessions, token_id,
                        name=symbol,
                        image=image_id,
                    )

    # ------------------------------------------------------------------
    # Control token handlers
    # ------------------------------------------------------------------

    async def _handle_home(self, session: Session, agent_id: str,
                           all_sessions: dict[str, Session]) -> None:
        """Send agent back to home matrix."""
        if hasattr(session, '_server') and session._server:
            await session._server.move_agent_to_matrix(
                session, agent_id,
                session._server.home_matrix_id)

    async def _handle_help(self, session: Session, agent_id: str) -> None:
        """Send help message to the clicking agent."""
        help_text = (
            "PairPanicking: A multiplayer memory game! "
            "Click hidden tiles (???) to reveal symbols. "
            "Match pairs to score points! "
            "Match: +2 all players, +4 bonus for you. "
            "Mismatch: -1 all active players, -1 extra for you. "
            "Game ends when all tiles are matched or all players are eliminated. "
            "Good luck!"
        )
        await session.send_hear(self.matrix_id, agent_id, help_text)

    async def _handle_restart(self, session: Session, agent_id: str,
                              all_sessions: dict[str, Session]) -> None:
        """Restart the game."""
        if self.game_in_progress:
            await session.send_hear(
                self.matrix_id, agent_id,
                "A game is already in progress!")
            return

        # Deduct 1 point from restarting player (spec rule 7.2)
        if agent_id in self.scores:
            self.scores[agent_id] -= 1
            agent = self.world.get_agent(agent_id)
            if agent:
                agent.energy = self.scores[agent_id]
            await self._broadcast_set(
                all_sessions, agent_id, energy=self.scores[agent_id])

        agent = self.world.get_agent(agent_id)
        name = agent.name if agent else agent_id
        await self._broadcast_hear(
            all_sessions, self.matrix_id, self.matrix_id,
            f"{name} started a new game!")

        await self._reset_game(all_sessions)

    # ------------------------------------------------------------------
    # Broadcast helpers
    # ------------------------------------------------------------------

    async def _broadcast_set(self, all_sessions: dict[str, Session],
                             objid: str, **attrs) -> None:
        """Send a set message to all agents in this matrix."""
        for agent in self.world.get_agents_in_matrix(self.matrix_id):
            session = all_sessions.get(agent.objid)
            if session:
                try:
                    await session.send_set(objid, **attrs)
                except Exception:
                    log.exception("Error broadcasting set to %s", agent.objid)

    async def _broadcast_hear(self, all_sessions: dict[str, Session],
                              from_id: str, to_id: str,
                              message: str) -> None:
        """Send a hear message to all agents in this matrix."""
        for agent in self.world.get_agents_in_matrix(self.matrix_id):
            session = all_sessions.get(agent.objid)
            if session:
                try:
                    await session.send_hear(from_id, to_id, message)
                except Exception:
                    log.exception("Error broadcasting hear to %s", agent.objid)
