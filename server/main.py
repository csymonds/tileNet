"""
TileNet Server - Entry point.

Usage:
    python -m server.main [--host HOST] [--port PORT]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys

from server.world import World
from server.server import TileNetServer
from server.games.home import HomePlugin

log = logging.getLogger(__name__)


async def setup_world(server: TileNetServer) -> None:
    """Initialize the world with a home matrix and game matrices."""
    world = server.world

    # Create home matrix (4 cols x 4 rows — a simple lobby)
    home = world.create_matrix(
        name="Home",
        cols=4, rows=4,
        bgcolor="ff1a1a2e",
        fgcolor="ffffffff",
        text="Welcome to TileNet! Choose a game to play.",
    )
    server.home_matrix_id = home.objid

    home_plugin = HomePlugin(world, home.objid)
    world.register_plugin(home.objid, home_plugin)

    # Create PairPanicking matrix (9 cols x 8 rows per spec)
    pp_matrix = world.create_matrix(
        name="PairPanicking",
        cols=9, rows=8,
        bgcolor="ff0a0a1a",
        fgcolor="ffffffff",
        text="PairPanicking - A multiplayer memory game!",
    )

    from server.games.pair_panicking import PairPanickingPlugin
    pp_plugin = PairPanickingPlugin(world, pp_matrix.objid)
    world.register_plugin(pp_matrix.objid, pp_plugin)

    # Run async plugin initialization
    await home_plugin.initialize({})
    await pp_plugin.initialize({})

    # Register navigation from home to PairPanicking
    home_plugin.register_nav_token(home_plugin.pp_token_id, pp_matrix.objid)


async def run_server(args: argparse.Namespace) -> None:
    """Async entry point — sets up the world, installs signal handlers, runs server."""
    world = World()
    server = TileNetServer(world, host=args.host, port=args.port)

    await setup_world(server)

    loop = asyncio.get_running_loop()

    # Install signal handlers so Ctrl+C triggers a clean shutdown
    def _request_shutdown():
        log.info("Shutdown requested (Ctrl+C)")
        server.shutdown()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_shutdown)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler; fall back to
            # the default signal module handler which raises KeyboardInterrupt
            signal.signal(sig, lambda s, f: _request_shutdown())

    log.info("Starting TileNet server on %s:%d", args.host, args.port)
    await server.start()


def main():
    parser = argparse.ArgumentParser(description="TileNet Server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address")
    parser.add_argument("--port", type=int, default=44455, help="Port number")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Windows asyncio fix for Python < 3.12
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
        asyncio.run(run_server(args))
    except KeyboardInterrupt:
        log.info("Server shut down")


if __name__ == "__main__":
    main()
