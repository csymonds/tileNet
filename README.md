# TileNet

A multiplayer real-time game framework built with Python, WebSockets, and Pygame.

TileNet is a client-server architecture where a WebSocket server hosts game worlds made up of grid-based matrices, and Pygame clients connect to play. The framework supports pluggable game modules -- currently shipping with **PairPanicking**, a multiplayer memory/concentration game.

Note: tileNet is based on a specification written by Prof. David Ackley for the UNM CS program in 2013. Credit for the design of tileNet goes to him. I tasked Claude Opus 4.5 with implementing a Python version to help motivate my daughter to learn Python and have fun by making games for tileNet.

## Project Structure

```
tileNet/
  tilenet/          # Shared protocol and object definitions
    protocol.py     # JSON message builders (server/client)
    objects.py      # Dataclass models (Matrix, Agent, Token, Key, Image)
  server/           # WebSocket game server
    main.py         # Server entry point
    server.py       # Connection handling and session lifecycle
    world.py        # Server-side world state
    session.py      # Per-client session management
    game_plugin.py  # Abstract base class for game logic
    games/          # Game implementations
      home.py       # Lobby with navigation to games
      pair_panicking.py  # Multiplayer memory game
  client/           # Pygame client
    main.py         # Client entry point and main loop
    network.py      # WebSocket connection (background thread)
    object_cache.py # Client-side object cache with protocol semantics
    ui.py           # Login, chat, and sidebar UI panels
    renderer.py     # Grid rendering and click detection
    assets.py       # Image decoding and caching
  PP Images/        # Symbol images for PairPanicking (16 JPEGs)
```

## Requirements

- Python 3.10+
- Dependencies: `websockets`, `pygame-ce`, `pygame-gui`

## Setup

1. Clone the repository:

   ```bash
   git clone https://github.com/csymonds/tileNet.git
   cd tileNet
   ```

2. Create and activate a virtual environment:

   ```bash
   python -m venv venv

   # Windows (Git Bash)
   source venv/Scripts/activate

   # Windows (cmd)
   venv\Scripts\activate

   # macOS / Linux
   source venv/bin/activate
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

## Running

### Start the server

```bash
python -m server.main
```

The server listens on `0.0.0.0:44455` by default. Options:

```
--host HOST    Bind address (default: 0.0.0.0)
--port PORT    Port number (default: 44455)
--debug        Enable debug logging
```

Stop the server with **Ctrl+C**.

### Start the client

In a separate terminal (with the venv activated):

```bash
python -m client.main
```

The client opens a Pygame window. Enter the server host and port on the connect screen, then log in with any username.

### Connecting to a remote server

To connect to a server running on another machine (e.g. an EC2 instance), enter its IP address on the client's connect screen instead of `localhost`. Make sure port 44455 is open in the server's firewall / security group.

## How to Play PairPanicking

1. Connect and log in
2. Click the **PairPanicking** tile in the Home lobby
3. Click **New Game** in the right column to start
4. Click hidden tiles (`???`) to reveal symbols -- find matching pairs
5. **Match:** +2 points for all players, +4 bonus for the revealer
6. **Mismatch:** -1 point for all active players, -1 extra for the revealer
7. Reach 0 points and you're eliminated
8. Game ends when all 64 tiles are matched or all players are eliminated

## Controls

| Key       | Action                                      |
|-----------|---------------------------------------------|
| Tab       | Cycle focus between form fields and buttons |
| Enter     | Submit the current form / send chat message |
| Mouse     | Click grid tiles, buttons, and UI elements  |
