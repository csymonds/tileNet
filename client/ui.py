"""
TileNet Client UI - pygame-gui based panels for login, chat, and agent list.

Manages the state machine: connect -> login -> playing
and the UI chrome around the game grid.
"""

from __future__ import annotations

import logging
import queue
from typing import Any

import pygame
import pygame_gui
from pygame_gui.elements import (
    UITextEntryLine,
    UIButton,
    UITextBox,
    UILabel,
)

from tilenet.protocol import make_login, make_cmd, make_logout, CMD_CLICK, CMD_SAY

log = logging.getLogger(__name__)

# Layout constants
WINDOW_WIDTH = 1024
WINDOW_HEIGHT = 768
SIDEBAR_WIDTH = 300
GRID_AREA_WIDTH = WINDOW_WIDTH - SIDEBAR_WIDTH
GRID_TOP_MARGIN = 30  # space for title above grid


class UIManager:
    """Manages all pygame-gui UI elements and state transitions."""

    def __init__(self, gui_manager: pygame_gui.UIManager,
                 screen: pygame.Surface):
        self.gui = gui_manager
        self.screen = screen

        # Current state
        self.state = "connect"  # connect -> login -> playing

        # Chat history
        self.chat_messages: list[str] = []
        self.max_chat_messages = 100

        # Status message
        self.status_message: str = ""

        # UI element references (created per state)
        self._connect_elements: dict[str, Any] = {}
        self._login_elements: dict[str, Any] = {}
        self._playing_elements: dict[str, Any] = {}

        # Tab order: list of focusable elements for current screen
        self._tab_order: list[Any] = []

        self._build_connect_ui()

    # ------------------------------------------------------------------
    # Connect Screen
    # ------------------------------------------------------------------

    def _build_connect_ui(self):
        self._clear_all()

        cx = WINDOW_WIDTH // 2 - 150
        cy = WINDOW_HEIGHT // 2 - 100

        UILabel(
            relative_rect=pygame.Rect(cx, cy - 60, 300, 30),
            text="TileNet",
            manager=self.gui,
        )

        UILabel(
            relative_rect=pygame.Rect(cx, cy, 80, 30),
            text="Host:",
            manager=self.gui,
        )
        host_input = UITextEntryLine(
            relative_rect=pygame.Rect(cx + 85, cy, 215, 30),
            manager=self.gui,
        )
        host_input.set_text("localhost")

        UILabel(
            relative_rect=pygame.Rect(cx, cy + 40, 80, 30),
            text="Port:",
            manager=self.gui,
        )
        port_input = UITextEntryLine(
            relative_rect=pygame.Rect(cx + 85, cy + 40, 215, 30),
            manager=self.gui,
        )
        port_input.set_text("44455")

        connect_btn = UIButton(
            relative_rect=pygame.Rect(cx + 75, cy + 90, 150, 40),
            text="Connect",
            manager=self.gui,
        )

        status_label = UILabel(
            relative_rect=pygame.Rect(cx, cy + 140, 300, 30),
            text="",
            manager=self.gui,
        )

        self._connect_elements = {
            "host": host_input,
            "port": port_input,
            "connect_btn": connect_btn,
            "status": status_label,
        }
        self._tab_order = [host_input, port_input, connect_btn]

    def _build_login_ui(self):
        self._clear_all()

        cx = WINDOW_WIDTH // 2 - 150
        cy = WINDOW_HEIGHT // 2 - 80

        UILabel(
            relative_rect=pygame.Rect(cx, cy - 60, 300, 30),
            text="Login to TileNet",
            manager=self.gui,
        )

        UILabel(
            relative_rect=pygame.Rect(cx, cy, 100, 30),
            text="Username:",
            manager=self.gui,
        )
        user_input = UITextEntryLine(
            relative_rect=pygame.Rect(cx + 105, cy, 195, 30),
            manager=self.gui,
        )

        UILabel(
            relative_rect=pygame.Rect(cx, cy + 40, 100, 30),
            text="Password:",
            manager=self.gui,
        )
        pass_input = UITextEntryLine(
            relative_rect=pygame.Rect(cx + 105, cy + 40, 195, 30),
            manager=self.gui,
        )

        login_btn = UIButton(
            relative_rect=pygame.Rect(cx + 75, cy + 90, 150, 40),
            text="Login",
            manager=self.gui,
        )

        status_label = UILabel(
            relative_rect=pygame.Rect(cx, cy + 140, 300, 30),
            text="",
            manager=self.gui,
        )

        server_info = UILabel(
            relative_rect=pygame.Rect(cx, cy - 30, 300, 25),
            text=self.status_message,
            manager=self.gui,
        )

        self._login_elements = {
            "user": user_input,
            "password": pass_input,
            "login_btn": login_btn,
            "status": status_label,
            "server_info": server_info,
        }
        self._tab_order = [user_input, pass_input, login_btn]

    def _build_playing_ui(self):
        self._clear_all()

        # Sidebar background
        sidebar_x = GRID_AREA_WIDTH
        panel_width = SIDEBAR_WIDTH - 10

        # -- Agent list label --
        UILabel(
            relative_rect=pygame.Rect(sidebar_x + 5, 5, panel_width, 25),
            text="Players",
            manager=self.gui,
        )

        agent_list = UITextBox(
            relative_rect=pygame.Rect(sidebar_x + 5, 32, panel_width, 200),
            html_text="",
            manager=self.gui,
        )

        # -- Chat panel --
        UILabel(
            relative_rect=pygame.Rect(sidebar_x + 5, 240, panel_width, 25),
            text="Chat",
            manager=self.gui,
        )

        chat_box = UITextBox(
            relative_rect=pygame.Rect(sidebar_x + 5, 267, panel_width, 400),
            html_text="",
            manager=self.gui,
        )

        # Chat input
        chat_input = UITextEntryLine(
            relative_rect=pygame.Rect(sidebar_x + 5, 675, panel_width - 55, 30),
            manager=self.gui,
        )

        send_btn = UIButton(
            relative_rect=pygame.Rect(sidebar_x + panel_width - 45, 675, 50, 30),
            text="Send",
            manager=self.gui,
        )

        # Disconnect button
        disconnect_btn = UIButton(
            relative_rect=pygame.Rect(sidebar_x + 5, 715, panel_width, 30),
            text="Disconnect",
            manager=self.gui,
        )

        self._playing_elements = {
            "agent_list": agent_list,
            "chat_box": chat_box,
            "chat_input": chat_input,
            "send_btn": send_btn,
            "disconnect_btn": disconnect_btn,
        }

    def _clear_all(self):
        """Remove all current UI elements."""
        self.gui.clear_and_reset()

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def transition_to_login(self, server_info: str = ""):
        self.state = "login"
        self.status_message = server_info
        self._build_login_ui()

    def transition_to_playing(self):
        self.state = "playing"
        self.chat_messages.clear()
        self._build_playing_ui()

    def transition_to_connect(self, error: str = ""):
        self.state = "connect"
        self.status_message = error
        self._build_connect_ui()
        if error and "status" in self._connect_elements:
            self._connect_elements["status"].set_text(error)

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event,
                     outgoing: queue.Queue,
                     cache: Any) -> dict[str, Any] | None:
        """Handle a pygame event. Returns a dict with action info or None.

        Possible return values:
            {"action": "connect", "host": ..., "port": ...}
            {"action": "login", "user": ..., "password": ...}
            {"action": "say", "text": ...}
            {"action": "disconnect"}
            None (no action needed)
        """
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            return self._handle_button(event, outgoing, cache)

        if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
            return self._handle_enter(event, outgoing, cache)

        if event.type == pygame.KEYDOWN and event.key == pygame.K_TAB:
            self._handle_tab()
            return None

        return None

    def _handle_button(self, event, outgoing, cache) -> dict | None:
        if self.state == "connect":
            btn = self._connect_elements.get("connect_btn")
            if event.ui_element == btn:
                host = self._connect_elements["host"].get_text().strip()
                port_str = self._connect_elements["port"].get_text().strip()
                try:
                    port = int(port_str)
                except ValueError:
                    self._connect_elements["status"].set_text("Invalid port")
                    return None
                return {"action": "connect", "host": host, "port": port}

        elif self.state == "login":
            btn = self._login_elements.get("login_btn")
            if event.ui_element == btn:
                user = self._login_elements["user"].get_text().strip()
                password = self._login_elements["password"].get_text()
                if not user:
                    self._login_elements["status"].set_text("Enter a username")
                    return None
                return {"action": "login", "user": user, "password": password}

        elif self.state == "playing":
            send_btn = self._playing_elements.get("send_btn")
            disconnect_btn = self._playing_elements.get("disconnect_btn")

            if event.ui_element == send_btn:
                return self._send_chat(outgoing, cache)
            elif event.ui_element == disconnect_btn:
                return {"action": "disconnect"}

        return None

    def _handle_enter(self, event, outgoing, cache) -> dict | None:
        if self.state == "connect":
            host = self._connect_elements["host"].get_text().strip()
            port_str = self._connect_elements["port"].get_text().strip()
            try:
                port = int(port_str)
            except ValueError:
                return None
            return {"action": "connect", "host": host, "port": port}

        elif self.state == "login":
            user = self._login_elements["user"].get_text().strip()
            password = self._login_elements["password"].get_text()
            if user:
                return {"action": "login", "user": user, "password": password}

        elif self.state == "playing":
            # Check if chat input is focused
            chat_input = self._playing_elements.get("chat_input")
            if chat_input and chat_input.is_focused:
                return self._send_chat(outgoing, cache)

        return None

    def _handle_tab(self) -> None:
        """Cycle focus through the tab order for the current screen."""
        if not self._tab_order:
            return

        # Find which element currently has focus
        current_idx = -1
        for i, elem in enumerate(self._tab_order):
            if isinstance(elem, UITextEntryLine) and elem.is_focused:
                current_idx = i
                break
            elif isinstance(elem, UIButton) and elem.is_focused:
                current_idx = i
                break

        # Move to next element
        next_idx = (current_idx + 1) % len(self._tab_order)
        next_elem = self._tab_order[next_idx]

        # Unfocus all, then focus the target
        for elem in self._tab_order:
            if isinstance(elem, UITextEntryLine):
                elem.unfocus()
            elif isinstance(elem, UIButton):
                elem.unselect()

        if isinstance(next_elem, UITextEntryLine):
            next_elem.focus()
        elif isinstance(next_elem, UIButton):
            next_elem.select()

    def _send_chat(self, outgoing, cache) -> dict | None:
        chat_input = self._playing_elements.get("chat_input")
        if not chat_input:
            return None
        text = chat_input.get_text().strip()
        if not text:
            return None
        chat_input.set_text("")
        return {"action": "say", "text": text}

    # ------------------------------------------------------------------
    # Update displays
    # ------------------------------------------------------------------

    def add_chat_message(self, from_name: str, message: str):
        """Add a message to the chat history and update display."""
        line = f"<b>{from_name}:</b> {message}" if from_name else message
        self.chat_messages.append(line)
        if len(self.chat_messages) > self.max_chat_messages:
            self.chat_messages = self.chat_messages[-self.max_chat_messages:]
        self._refresh_chat()

    def _refresh_chat(self):
        chat_box = self._playing_elements.get("chat_box")
        if chat_box:
            html = "<br>".join(self.chat_messages)
            chat_box.set_text(html)
            # Scroll to bottom
            chat_box.scroll_bar.set_scroll_from_start_percentage(1.0) if hasattr(chat_box, 'scroll_bar') and chat_box.scroll_bar else None

    def update_agent_list(self, cache: Any):
        """Update the agent list panel from the object cache."""
        agent_list = self._playing_elements.get("agent_list")
        if not agent_list:
            return

        agents = cache.get_matrix_agents()
        lines = []
        for agent in agents:
            name = agent.get("name", "?")
            energy = agent.get("energy", 0)
            is_me = agent.get("objid") == cache.my_agent_id
            marker = " (you)" if is_me else ""
            active = "active" if energy > 0 else "out"
            lines.append(f"<b>{name}{marker}</b>: {energy} pts ({active})")

        html = "<br>".join(lines) if lines else "<i>No players</i>"
        agent_list.set_text(html)

    def set_login_status(self, message: str):
        """Update the status label on the login screen."""
        status = self._login_elements.get("status")
        if status:
            status.set_text(message)

    def set_connect_status(self, message: str):
        """Update the status label on the connect screen."""
        status = self._connect_elements.get("status")
        if status:
            status.set_text(message)

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def draw_sidebar_background(self):
        """Draw the sidebar background when in playing state."""
        if self.state == "playing":
            sidebar_rect = pygame.Rect(
                GRID_AREA_WIDTH, 0, SIDEBAR_WIDTH, WINDOW_HEIGHT)
            pygame.draw.rect(self.screen, (25, 25, 35), sidebar_rect)

    def is_chat_focused(self) -> bool:
        """Check if the chat input has focus (suppress key presses)."""
        if self.state == "playing":
            chat_input = self._playing_elements.get("chat_input")
            if chat_input:
                return chat_input.is_focused
        return False
