"""
TileNet Client Network - WebSocket connection in a background thread.

Communicates with the main Pygame thread via thread-safe queues:
  incoming_queue: server messages -> main thread
  outgoing_queue: main thread commands -> server
"""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
import sys

log = logging.getLogger(__name__)


class NetworkThread(threading.Thread):
    """Background thread managing the WebSocket connection."""

    def __init__(self, host: str, port: int,
                 incoming: queue.Queue, outgoing: queue.Queue):
        super().__init__(daemon=True, name="TileNet-Network")
        self.host = host
        self.port = port
        self.incoming = incoming
        self.outgoing = outgoing
        self.running = True
        self._connected = threading.Event()
        self.error: str | None = None

    def run(self):
        """Thread entry point — runs the async WebSocket loop."""
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(
                asyncio.WindowsSelectorEventLoopPolicy())
        try:
            asyncio.run(self._run_async())
        except Exception as e:
            self.error = str(e)
            log.exception("Network thread error")
            # Push an error notification to the main thread
            self.incoming.put({"type": "_error", "message": str(e)})

    async def _run_async(self):
        import websockets
        uri = f"ws://{self.host}:{self.port}"
        log.info("Connecting to %s", uri)
        try:
            async with websockets.connect(uri) as ws:
                self._connected.set()
                log.info("Connected to server")

                recv_task = asyncio.create_task(self._recv_loop(ws))
                send_task = asyncio.create_task(self._send_loop(ws))

                done, pending = await asyncio.wait(
                    [recv_task, send_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )

                for task in pending:
                    task.cancel()

        except Exception as e:
            log.error("Connection failed: %s", e)
            self.incoming.put({"type": "_error", "message": str(e)})

    async def _recv_loop(self, ws):
        """Receive messages from server and put them in the incoming queue."""
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                    self.incoming.put(msg)
                except json.JSONDecodeError:
                    log.warning("Invalid JSON from server: %s", raw[:100])
        except Exception as e:
            log.info("Recv loop ended: %s", e)
            self.incoming.put({"type": "_disconnected", "message": str(e)})

    async def _send_loop(self, ws):
        """Read from outgoing queue and send to server."""
        loop = asyncio.get_running_loop()
        while self.running:
            try:
                msg = await loop.run_in_executor(
                    None, self._blocking_get
                )
                if msg is None:
                    continue
                raw = json.dumps(msg, separators=(",", ":"))
                log.debug("Sending: %s", raw[:200])
                await ws.send(raw)
                log.debug("Sent OK")
            except Exception as e:
                log.info("Send loop ended: %s", e)
                break

    def _blocking_get(self):
        """Blocking queue get with timeout — runs in executor thread."""
        try:
            return self.outgoing.get(timeout=0.1)
        except queue.Empty:
            return None

    def wait_connected(self, timeout: float = 5.0) -> bool:
        """Block until connected or timeout."""
        return self._connected.wait(timeout)

    def stop(self):
        self.running = False
