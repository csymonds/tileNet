"""
TileNet Client Renderer - Pygame grid rendering and hit testing.

Draws the current matrix as a grid of colored cells with text labels
and optional image icons. Handles mouse click -> token objid mapping.
"""

from __future__ import annotations

import logging
from typing import Any

import pygame

from client.object_cache import ObjectCache
from client.assets import AssetManager

log = logging.getLogger(__name__)

# Rendering constants
CELL_PADDING = 2
FONT_SIZE = 14
TITLE_FONT_SIZE = 20
MIN_CELL_SIZE = 40


def parse_rgba(hex_str: str) -> tuple[int, int, int, int]:
    """Parse an 8-char RGBA hex string into (r, g, b, a) tuple."""
    try:
        val = int(hex_str, 16)
        r = (val >> 24) & 0xFF
        g = (val >> 16) & 0xFF
        b = (val >> 8) & 0xFF
        a = val & 0xFF
        return (r, g, b, a)
    except (ValueError, TypeError):
        return (100, 100, 100, 255)


class GridRenderer:
    """Renders the TileNet matrix grid using Pygame."""

    def __init__(self, screen: pygame.Surface, grid_rect: pygame.Rect,
                 assets: AssetManager):
        self.screen = screen
        self.grid_rect = grid_rect
        self.assets = assets
        self.font: pygame.font.Font | None = None
        self.title_font: pygame.font.Font | None = None
        self._ensure_fonts()

    def _ensure_fonts(self):
        if not self.font:
            self.font = pygame.font.SysFont("consolas", FONT_SIZE)
        if not self.title_font:
            self.title_font = pygame.font.SysFont("consolas", TITLE_FONT_SIZE, bold=True)

    def draw(self, cache: ObjectCache) -> None:
        """Draw the entire matrix grid."""
        self._ensure_fonts()

        matrix = cache.get_current_matrix()
        if not matrix:
            # Draw placeholder
            text = self.title_font.render("No matrix loaded", True, (200, 200, 200))
            self.screen.blit(text, (self.grid_rect.x + 20, self.grid_rect.y + 20))
            return

        cols = matrix.get("x", 2)
        rows = matrix.get("y", 2)
        cell_w = max(MIN_CELL_SIZE, self.grid_rect.width // cols)
        cell_h = max(MIN_CELL_SIZE, self.grid_rect.height // rows)

        # Draw matrix background
        bg = parse_rgba(matrix.get("bgcolor", "ff333333"))
        pygame.draw.rect(self.screen, bg[:3],
                         (self.grid_rect.x, self.grid_rect.y,
                          cols * cell_w, rows * cell_h))

        # Draw title above grid
        title = matrix.get("name", "")
        if title:
            fg = parse_rgba(matrix.get("fgcolor", "ffffffff"))
            title_surf = self.title_font.render(title, True, fg[:3])
            self.screen.blit(title_surf,
                             (self.grid_rect.x + 5,
                              self.grid_rect.y - TITLE_FONT_SIZE - 5))

        # Draw tokens
        for token in cache.get_matrix_tokens():
            tx = token.get("x", 0)
            ty = token.get("y", 0)
            if tx < 0:
                continue  # exited

            rect = pygame.Rect(
                self.grid_rect.x + tx * cell_w + CELL_PADDING,
                self.grid_rect.y + ty * cell_h + CELL_PADDING,
                cell_w - CELL_PADDING * 2,
                cell_h - CELL_PADDING * 2,
            )

            # Background color
            bgcolor = parse_rgba(token.get("bgcolor", "ff444444"))
            energy = token.get("energy", 1)

            # Draw the cell background
            if bgcolor[3] > 0:  # has some alpha
                cell_surface = pygame.Surface((rect.width, rect.height),
                                              pygame.SRCALPHA)
                cell_surface.fill(bgcolor)
                self.screen.blit(cell_surface, rect.topleft)
            else:
                pygame.draw.rect(self.screen, bgcolor[:3], rect)

            # Draw border for enabled tokens
            if energy > 0:
                pygame.draw.rect(self.screen, (80, 80, 80), rect, 1)
            else:
                pygame.draw.rect(self.screen, (40, 40, 40), rect, 1)

            # Draw image if present
            image_id = token.get("image", "")
            if image_id:
                surface = self.assets.get_surface(image_id)
                if surface:
                    # Scale to fit cell (with small margin)
                    margin = 4
                    img_w = rect.width - margin * 2
                    img_h = rect.height - margin * 2
                    if img_w > 0 and img_h > 0:
                        scaled = pygame.transform.smoothscale(
                            surface, (img_w, img_h))
                        self.screen.blit(scaled,
                                         (rect.x + margin, rect.y + margin))
                    continue  # skip text if image is shown

            # Draw name text (centered in cell)
            name = token.get("name", "")
            if name:
                fgcolor = parse_rgba(token.get("fgcolor", "ffffffff"))
                text_surf = self.font.render(name, True, fgcolor[:3])
                text_rect = text_surf.get_rect(center=rect.center)
                self.screen.blit(text_surf, text_rect)

        # Draw agents as small indicators (bottom-left of their positions,
        # if they have x/y — but TileNet agents don't typically have grid positions)
        # Instead, agents are shown in the sidebar agent list.

    def hit_test(self, pos: tuple[int, int],
                 cache: ObjectCache) -> str | None:
        """Return the token objid at the given mouse position, or None."""
        matrix = cache.get_current_matrix()
        if not matrix:
            return None

        cols = matrix.get("x", 2)
        rows = matrix.get("y", 2)
        cell_w = max(MIN_CELL_SIZE, self.grid_rect.width // cols)
        cell_h = max(MIN_CELL_SIZE, self.grid_rect.height // rows)

        mx, my = pos
        # Check if within grid bounds
        gx = mx - self.grid_rect.x
        gy = my - self.grid_rect.y
        if gx < 0 or gy < 0 or gx >= cols * cell_w or gy >= rows * cell_h:
            return None

        col = gx // cell_w
        row = gy // cell_h

        # Find token at this position
        for token in cache.get_matrix_tokens():
            tx = token.get("x", -1)
            ty = token.get("y", -1)
            if tx == col and ty == row:
                return token.get("objid")

        return None
