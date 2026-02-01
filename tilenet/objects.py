"""
TileNet Object Model.

Defines the five TileNet object types as dataclasses:
  Matrix  - A 2D grid container (rooms/boards)
  Agent   - Represents a connected player
  Token   - Clickable objects placed in grid cells
  Key     - Keyboard bindings
  ImageObj - Image data (icon/background)

Each object has an objid and a set of attributes that can be
updated via 'set' messages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# Default colors (RGBA hex, fully opaque)
DEFAULT_BGCOLOR = "ff333333"
DEFAULT_FGCOLOR = "ffffffff"
DEFAULT_ENERGY = 1


@dataclass
class TileNetObject:
    """Base class for all TileNet objects."""
    objid: str
    name: str = ""
    text: str = ""
    energy: int = DEFAULT_ENERGY
    bgcolor: str = DEFAULT_BGCOLOR
    fgcolor: str = DEFAULT_FGCOLOR
    x: int = 0
    y: int = 0
    image: str = ""  # objid of an ImageObj, or "" for none

    def to_set_attrs(self) -> dict[str, Any]:
        """Return all non-default attributes as a dict suitable for a set message."""
        attrs: dict[str, Any] = {}
        if self.name:
            attrs["name"] = self.name
        if self.text:
            attrs["text"] = self.text
        if self.energy != DEFAULT_ENERGY:
            attrs["energy"] = self.energy
        if self.bgcolor != DEFAULT_BGCOLOR:
            attrs["bgcolor"] = self.bgcolor
        if self.fgcolor != DEFAULT_FGCOLOR:
            attrs["fgcolor"] = self.fgcolor
        if self.x != 0:
            attrs["x"] = self.x
        if self.y != 0:
            attrs["y"] = self.y
        if self.image:
            attrs["image"] = self.image
        return attrs

    def to_full_set_attrs(self) -> dict[str, Any]:
        """Return ALL attributes as a dict (for full object definition)."""
        return {
            "name": self.name,
            "text": self.text,
            "energy": self.energy,
            "bgcolor": self.bgcolor,
            "fgcolor": self.fgcolor,
            "x": self.x,
            "y": self.y,
            "image": self.image,
        }

    def apply_attrs(self, attrs: dict[str, Any]) -> None:
        """Apply attribute updates from a set message."""
        for key in ("name", "text", "energy", "bgcolor", "fgcolor", "x", "y", "image"):
            if key in attrs:
                setattr(self, key, attrs[key])


@dataclass
class Matrix(TileNetObject):
    """A 2D grid container. x = columns, y = rows."""
    # Override defaults for matrices: x and y represent grid dimensions
    # (must be > 1 per spec)

    def __post_init__(self):
        if self.x < 2:
            self.x = 2
        if self.y < 2:
            self.y = 2


@dataclass
class Agent(TileNetObject):
    """Represents a connected player's avatar in the world."""
    container_matrix: str = ""  # objid of the matrix this agent is in


@dataclass
class Token(TileNetObject):
    """A clickable object placed in a grid cell.
    x = column, y = row within the containing matrix.
    """
    container_matrix: str = ""


@dataclass
class Key(TileNetObject):
    """A keyboard binding. name = the key name (e.g., 'VK_SPACE')."""
    container_matrix: str = ""


@dataclass
class ImageObj(TileNetObject):
    """Image data. text = hex-encoded image bytes.
    x = pixel width, y = pixel height.
    """
    pass
