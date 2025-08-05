from world.tile import wall

class GameMap:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        # Initialize with walls
        self.tiles = [[wall for _ in range(width)] for _ in range(height)]
        self.items_on_ground = [] # <--- NEW: List to hold items dropped or generated on the map

    def is_walkable(self, x, y):
        """Check if a position is walkable"""
        if 0 <= x < self.width and 0 <= y < self.height:
            return not self.tiles[y][x].blocked
        return False

    def render(self, screen, tile_size, font):
        """Render the map"""
        for y in range(self.height):
            for x in range(self.width):
                tile = self.tiles[y][x]
                char_surface = font.render(tile.char, True, tile.color)
                screen.blit(char_surface, (x * tile_size, y * tile_size))
