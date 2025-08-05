# MultipleFiles/fov.py
import math

class FOV:
    def __init__(self, game_map):
        self.game_map = game_map
        # visible will now store (x, y) -> light_source_type (e.g., 'player', 'torch')
        self.visible_sources = {}
        self.explored = set()
    
    def compute_fov(self, origin_x, origin_y, radius=8, light_source_type='player'): # NEW: light_source_type
        """Compute field of view from origin point using simple raycasting"""
        
        # Origin is always visible
        self.visible_sources[(origin_x, origin_y)] = light_source_type
        self.explored.add((origin_x, origin_y))
        
        # Cast rays in all directions
        for angle in range(0, 360, 2):  # Every 2 degrees for good coverage
            self._cast_ray(origin_x, origin_y, angle, radius, light_source_type) # Pass source type
    
    def _cast_ray(self, start_x, start_y, angle, max_distance, light_source_type): # NEW: light_source_type
        """Cast a ray from start position at given angle"""
        rad = math.radians(angle)
        dx = math.cos(rad)
        dy = math.sin(rad)
        
        for i in range(max_distance + 1):
            x = int(start_x + dx * i)
            y = int(start_y + dy * i)
            
            if not (0 <= x < self.game_map.width and 0 <= y < self.game_map.height):
                break
            
            # If a tile is already lit by a 'player' source, don't downgrade it to 'torch'
            # Otherwise, set or update its source
            current_source = self.visible_sources.get((x, y))
            if current_source == 'player':
                pass # Player light always takes precedence
            elif current_source == 'torch' and light_source_type == 'player':
                self.visible_sources[(x, y)] = 'player' # Upgrade to player light
            else: # No source, or current source is 'torch' and new source is 'torch'
                self.visible_sources[(x, y)] = light_source_type

            self.explored.add((x, y))
            
            if self.game_map.tiles[y][x].block_sight:
                break
    
    def get_visibility_type(self, x, y): # NEW: Check visibility type
        """Returns 'player', 'torch', 'explored', or 'unexplored'"""
        if (x, y) in self.visible_sources:
            return self.visible_sources[(x, y)]
        elif (x, y) in self.explored:
            return 'explored'
        return 'unexplored'

    # is_visible and is_explored methods are now deprecated, use get_visibility_type
    # def is_visible(self, x, y):
    #     return (x, y) in self.visible
    
    # def is_explored(self, x, y):
    #     return (x, y) in self.explored
