"""
TileNet Client - Entry point.

Runs the Pygame main loop, manages the state machine
(connect -> login -> playing), and coordinates between
the UI, renderer, network thread, and object cache.

Usage:
    python -m client.main
"""

from __future__ import annotations

import logging
import queue
import sys
from typing import Any

import pygame
import pygame_gui

from client.network import NetworkThread
from client.object_cache import ObjectCache
from client.renderer import GridRenderer
from client.assets import AssetManager
from client.ui import UIManager, WINDOW_WIDTH, WINDOW_HEIGHT, GRID_AREA_WIDTH, GRID_TOP_MARGIN
from tilenet.protocol import make_login, make_cmd, make_logout, CMD_CLICK, CMD_SAY

log = logging.getLogger(__name__)


def main():
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    pygame.init()
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption("TileNet Client")
    clock = pygame.time.Clock()

    gui_manager = pygame_gui.UIManager((WINDOW_WIDTH, WINDOW_HEIGHT))

    # Core objects
    incoming: queue.Queue = queue.Queue()
    outgoing: queue.Queue = queue.Queue()
    cache = ObjectCache()
    assets = AssetManager()

    # Grid area: left portion of window, with top margin for title
    grid_rect = pygame.Rect(0, GRID_TOP_MARGIN,
                            GRID_AREA_WIDTH,
                            WINDOW_HEIGHT - GRID_TOP_MARGIN)

    ui = UIManager(gui_manager, screen)
    renderer = GridRenderer(screen, grid_rect, assets)
    network: NetworkThread | None = None

    # Server info (from hello message)
    server_group = ""
    server_name = ""

    running = True
    while running:
        dt = clock.tick(30) / 1000.0

        # -- Event handling --
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                break

            gui_manager.process_events(event)

            # UI event handling
            action = ui.handle_event(event, outgoing, cache)
            if action:
                action_type = action.get("action")

                if action_type == "connect":
                    # Stop any existing network thread before starting a new one
                    if network and network.is_alive():
                        network.stop()
                        network = None
                        # Drain any stale messages from the old connection
                        while not incoming.empty():
                            try:
                                incoming.get_nowait()
                            except queue.Empty:
                                break

                    host = action["host"]
                    port = action["port"]
                    ui.set_connect_status("Connecting...")
                    network = NetworkThread(host, port, incoming, outgoing)
                    network.start()

                elif action_type == "login":
                    user = action["user"]
                    password = action["password"]
                    outgoing.put(make_login(user, password))
                    ui.set_login_status("Logging in...")

                elif action_type == "say":
                    text = action["text"]
                    # Say to the current matrix (broadcast)
                    if cache.current_matrix_id and cache.my_agent_id:
                        # Find another agent to say to (for agent-to-agent chat)
                        # Default: say to own agent id, which broadcasts to matrix
                        target = cache.my_agent_id
                        agents = cache.get_matrix_agents()
                        if agents:
                            # Say to own agent -> server broadcasts to matrix
                            target = cache.my_agent_id
                        outgoing.put(make_cmd(CMD_SAY, target, text=text))

                elif action_type == "disconnect":
                    outgoing.put(make_logout())
                    if network:
                        network.stop()
                        network = None
                    cache = ObjectCache()
                    assets = AssetManager()
                    renderer = GridRenderer(screen, grid_rect, assets)
                    ui.transition_to_connect()

            # Grid clicks when playing
            if (ui.state == "playing"
                    and event.type == pygame.MOUSEBUTTONDOWN
                    and event.button == 1):
                # Check we're not clicking on UI elements
                if event.pos[0] < GRID_AREA_WIDTH:
                    token_id = renderer.hit_test(event.pos, cache)
                    if token_id:
                        token = cache.get_object(token_id)
                        if token and token.get("energy", 1) > 0:
                            outgoing.put(make_cmd(CMD_CLICK, token_id))

        # -- Process incoming messages --
        messages_this_frame = 0
        max_messages_per_frame = 50  # prevent stalling
        while not incoming.empty() and messages_this_frame < max_messages_per_frame:
            try:
                msg = incoming.get_nowait()
            except queue.Empty:
                break
            messages_this_frame += 1
            _process_message(msg, ui, cache, assets, outgoing,
                             locals())

        # -- Update --
        gui_manager.update(dt)

        if ui.state == "playing":
            ui.update_agent_list(cache)

        # -- Draw --
        screen.fill((20, 20, 28))

        if ui.state == "playing":
            renderer.draw(cache)
            ui.draw_sidebar_background()

        gui_manager.draw_ui(screen)
        pygame.display.flip()

    # -- Cleanup --
    if network:
        outgoing.put(make_logout())
        network.stop()
    pygame.quit()


def _process_message(msg: dict[str, Any], ui: UIManager,
                     cache: ObjectCache, assets: AssetManager,
                     outgoing: queue.Queue,
                     local_vars: dict) -> None:
    """Process a single message from the server."""
    msg_type = msg.get("type", "")
    log.debug("Processing message: type=%s", msg_type)

    if msg_type == "server":
        # Server hello — transition to login
        group = msg.get("group", "")
        name = msg.get("name", "")
        status = msg.get("status", "")
        info = f"{name} ({group}) - {status}"
        if status == "open":
            ui.transition_to_login(info)
        else:
            ui.transition_to_connect(f"Server {status}: {info}")

    elif msg_type == "logged-in":
        objid = msg.get("objid")
        message = msg.get("message", "")
        if objid:
            # Success
            cache.my_agent_id = objid
            ui.transition_to_playing()
            log.info("Logged in as %s: %s", objid, message)
        else:
            # Failure
            ui.set_login_status(message or "Login failed")

    elif msg_type == "set":
        objid, matrix_changed = cache.process_set(msg)

        # Check if this is an image definition (has hex data in text field)
        obj = cache.get_object(objid)
        if obj and obj.get("_type") == "i" and obj.get("text"):
            hex_data = obj["text"]
            width = obj.get("x", 64)
            height = obj.get("y", 64)
            if not assets.has_image(objid):
                assets.decode_image(objid, hex_data, width, height)

        if matrix_changed and ui.state == "playing":
            log.info("Matrix changed to %s", cache.current_matrix_id)

    elif msg_type == "hear":
        from_id = msg.get("from", "")
        to_id = msg.get("to", "")
        message = msg.get("message", "")

        # Look up sender name
        from_obj = cache.get_object(from_id)
        from_name = from_obj.get("name", from_id) if from_obj else from_id

        if ui.state == "playing":
            ui.add_chat_message(from_name, message)

    elif msg_type == "logged-out":
        message = msg.get("message", "Disconnected")
        log.info("Logged out: %s", message)
        ui.transition_to_connect(f"Logged out: {message}")
        cache.__init__()  # reset cache

    elif msg_type == "_error":
        error = msg.get("message", "Connection error")
        log.error("Network error: %s", error)
        if ui.state == "connect":
            ui.set_connect_status(f"Error: {error}")
        else:
            ui.transition_to_connect(f"Error: {error}")

    elif msg_type == "_disconnected":
        message = msg.get("message", "Disconnected")
        ui.transition_to_connect(f"Disconnected: {message}")
        cache.__init__()


if __name__ == "__main__":
    main()
