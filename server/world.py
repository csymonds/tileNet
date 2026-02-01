"""
TileNet World - Server-side world state management.

The World owns all TileNet objects (matrices, agents, tokens, keys, images),
generates unique objids, and tracks which objects are in which matrices.
"""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from tilenet.objects import (
    TileNetObject, Matrix, Agent, Token, Key, ImageObj,
    DEFAULT_BGCOLOR, DEFAULT_FGCOLOR, DEFAULT_ENERGY,
)
from tilenet.protocol import (
    OBJ_MATRIX, OBJ_AGENT, OBJ_TOKEN, OBJ_KEY, OBJ_IMAGE, obj_type,
)

if TYPE_CHECKING:
    from server.game_plugin import GamePlugin

log = logging.getLogger(__name__)


class World:
    """Server-side world state.

    All mutations go through World methods so that event ordering
    and object registry consistency are maintained.
    """

    def __init__(self):
        self.objects: dict[str, TileNetObject] = {}
        self.next_ids: dict[str, int] = {
            OBJ_MATRIX: 1,
            OBJ_AGENT: 1,
            OBJ_TOKEN: 1,
            OBJ_KEY: 1,
            OBJ_IMAGE: 1,
        }
        # matrix_id -> set of objids contained in that matrix
        self.matrix_contents: dict[str, set[str]] = {}
        # matrix_id -> GamePlugin (if any)
        self.game_plugins: dict[str, GamePlugin] = {}

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def new_objid(self, type_code: str) -> str:
        """Generate a new unique objid like 'm1', 't42', etc."""
        num = self.next_ids[type_code]
        self.next_ids[type_code] = num + 1
        return f"{type_code}{num}"

    # ------------------------------------------------------------------
    # Object creation
    # ------------------------------------------------------------------

    def create_matrix(self, name: str = "", cols: int = 2, rows: int = 2,
                      **attrs: Any) -> Matrix:
        objid = self.new_objid(OBJ_MATRIX)
        m = Matrix(objid=objid, name=name, x=cols, y=rows, **attrs)
        self.objects[objid] = m
        self.matrix_contents[objid] = set()
        log.info("Created matrix %s (%s) %dx%d", objid, name, cols, rows)
        return m

    def create_agent(self, name: str, text: str = "",
                     energy: int = DEFAULT_ENERGY) -> Agent:
        objid = self.new_objid(OBJ_AGENT)
        a = Agent(objid=objid, name=name, text=text, energy=energy)
        self.objects[objid] = a
        log.info("Created agent %s (%s)", objid, name)
        return a

    def create_token(self, name: str = "", x: int = 0, y: int = 0,
                     energy: int = DEFAULT_ENERGY, **attrs: Any) -> Token:
        objid = self.new_objid(OBJ_TOKEN)
        t = Token(objid=objid, name=name, x=x, y=y, energy=energy, **attrs)
        self.objects[objid] = t
        log.info("Created token %s (%s) at (%d,%d)", objid, name, x, y)
        return t

    def create_key(self, name: str = "", **attrs: Any) -> Key:
        objid = self.new_objid(OBJ_KEY)
        k = Key(objid=objid, name=name, **attrs)
        self.objects[objid] = k
        return k

    def create_image(self, hex_data: str = "", width: int = 64,
                     height: int = 64) -> ImageObj:
        objid = self.new_objid(OBJ_IMAGE)
        img = ImageObj(objid=objid, text=hex_data, x=width, y=height)
        self.objects[objid] = img
        log.info("Created image %s (%dx%d, %d hex chars)",
                 objid, width, height, len(hex_data))
        return img

    # ------------------------------------------------------------------
    # Object lookup
    # ------------------------------------------------------------------

    def get(self, objid: str) -> TileNetObject | None:
        return self.objects.get(objid)

    def get_matrix(self, objid: str) -> Matrix | None:
        obj = self.objects.get(objid)
        return obj if isinstance(obj, Matrix) else None

    def get_agent(self, objid: str) -> Agent | None:
        obj = self.objects.get(objid)
        return obj if isinstance(obj, Agent) else None

    def get_token(self, objid: str) -> Token | None:
        obj = self.objects.get(objid)
        return obj if isinstance(obj, Token) else None

    # ------------------------------------------------------------------
    # Matrix contents
    # ------------------------------------------------------------------

    def get_contents(self, matrix_id: str) -> set[str]:
        """Return the set of objids in a matrix."""
        return self.matrix_contents.get(matrix_id, set())

    def get_agents_in_matrix(self, matrix_id: str) -> list[Agent]:
        """Return all agents currently in a matrix."""
        result = []
        for oid in self.matrix_contents.get(matrix_id, set()):
            obj = self.objects.get(oid)
            if isinstance(obj, Agent):
                result.append(obj)
        return result

    def get_tokens_in_matrix(self, matrix_id: str) -> list[Token]:
        """Return all tokens currently in a matrix."""
        result = []
        for oid in self.matrix_contents.get(matrix_id, set()):
            obj = self.objects.get(oid)
            if isinstance(obj, Token):
                result.append(obj)
        return result

    def get_images_in_matrix(self, matrix_id: str) -> list[ImageObj]:
        """Return all images currently in a matrix."""
        result = []
        for oid in self.matrix_contents.get(matrix_id, set()):
            obj = self.objects.get(oid)
            if isinstance(obj, ImageObj):
                result.append(obj)
        return result

    def get_keys_in_matrix(self, matrix_id: str) -> list[Key]:
        """Return all keys currently in a matrix."""
        result = []
        for oid in self.matrix_contents.get(matrix_id, set()):
            obj = self.objects.get(oid)
            if isinstance(obj, Key):
                result.append(obj)
        return result

    # ------------------------------------------------------------------
    # Placement and removal
    # ------------------------------------------------------------------

    def place_in_matrix(self, objid: str, matrix_id: str) -> None:
        """Place an object into a matrix (updates internal tracking)."""
        # Remove from any current matrix first
        obj = self.objects.get(objid)
        if obj and hasattr(obj, "container_matrix") and obj.container_matrix:
            old = obj.container_matrix
            self.matrix_contents.get(old, set()).discard(objid)
        # Add to new matrix
        if matrix_id in self.matrix_contents:
            self.matrix_contents[matrix_id].add(objid)
        if obj and hasattr(obj, "container_matrix"):
            obj.container_matrix = matrix_id

    def remove_from_matrix(self, objid: str) -> str | None:
        """Remove an object from its current matrix. Returns the old matrix id."""
        obj = self.objects.get(objid)
        if obj and hasattr(obj, "container_matrix") and obj.container_matrix:
            old = obj.container_matrix
            self.matrix_contents.get(old, set()).discard(objid)
            obj.container_matrix = ""
            return old
        return None

    # ------------------------------------------------------------------
    # Game plugin management
    # ------------------------------------------------------------------

    def register_plugin(self, matrix_id: str, plugin: GamePlugin) -> None:
        self.game_plugins[matrix_id] = plugin

    def get_plugin(self, matrix_id: str) -> GamePlugin | None:
        return self.game_plugins.get(matrix_id)
