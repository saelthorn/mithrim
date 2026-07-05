import pygame

import graphics


def test_get_tile_surface_caches_surfaces():
    pygame.init()
    graphics.TILESET_IMAGE = pygame.Surface((24, 24), pygame.SRCALPHA)
    graphics.TILE_MAPPING = {".": (0, 0)}
    graphics._SURFACE_CACHE.clear()

    first = graphics.get_tile_surface(".")
    second = graphics.get_tile_surface(".")

    assert first is second
