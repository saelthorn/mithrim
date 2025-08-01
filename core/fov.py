import math

class FOV:
    def __init__(self, game_map):
        self.game_map = game_map
        self.visible = set()
        self.explored = set()
    
    def compute_fov(self, origin_x, origin_y, radius=8):
        """Compute field of view from origin point using simple raycasting"""
        self.visible.clear()
        
        # Origin is always visible
        self.visible.add((origin_x, origin_y))
        self.explored.add((origin_x, origin_y))
        
        # Cast rays in all directions
        for angle in range(0, 360, 2):  # Every 2 degrees for good coverage
            self._cast_ray(origin_x, origin_y, angle, radius)
    
    def _cast_ray(self, start_x, start_y, angle, max_distance):
        """Cast a ray from start position at given angle"""
        # Convert angle to radians
        rad = math.radians(angle)
        dx = math.cos(rad)
        dy = math.sin(rad)
        
        # Step along the ray
        for i in range(max_distance + 1):
            # Calculate current position
            x = int(start_x + dx * i)
            y = int(start_y + dy * i)
            
            # Check bounds
            if not (0 <= x < self.game_map.width and 0 <= y < self.game_map.height):
                break
            
            # Add to visible set
            self.visible.add((x, y))
            self.explored.add((x, y))
            
            # Stop if we hit a wall
            if self.game_map.tiles[y][x].block_sight:
                break
    
    def is_visible(self, x, y):
        """Check if a position is currently visible"""
        return (x, y) in self.visible
    
    def is_explored(self, x, y):
        """Check if a position has been explored"""
        return (x, y) in self.explored
