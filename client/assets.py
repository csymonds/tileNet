"""
TileNet Client Assets - Image decoding and caching.

Converts hex-encoded image data from TileNet image objects
into Pygame surfaces for rendering.
"""

from __future__ import annotations

import io
import logging

import pygame

log = logging.getLogger(__name__)


class AssetManager:
    """Manages decoded images for the client renderer."""

    def __init__(self):
        # image objid -> pygame.Surface
        self.surfaces: dict[str, pygame.Surface] = {}

    def decode_image(self, image_objid: str, hex_data: str,
                     width: int = 0, height: int = 0) -> pygame.Surface | None:
        """Decode hex-encoded image bytes into a Pygame Surface and cache it.

        Args:
            image_objid: The image object's objid (e.g., "i1")
            hex_data: Hex-encoded image file bytes
            width: Desired display width (0 = use native)
            height: Desired display height (0 = use native)

        Returns:
            The decoded Surface, or None on failure.
        """
        if not hex_data:
            return None

        try:
            raw_bytes = bytes.fromhex(hex_data)
            buffer = io.BytesIO(raw_bytes)
            surface = pygame.image.load(buffer)

            if width > 0 and height > 0:
                surface = pygame.transform.smoothscale(surface, (width, height))

            self.surfaces[image_objid] = surface
            log.debug("Decoded image %s (%d bytes)", image_objid, len(raw_bytes))
            return surface

        except Exception:
            log.exception("Failed to decode image %s", image_objid)
            return None

    def get_surface(self, image_objid: str) -> pygame.Surface | None:
        """Get a cached surface by image objid."""
        return self.surfaces.get(image_objid)

    def has_image(self, image_objid: str) -> bool:
        return image_objid in self.surfaces
