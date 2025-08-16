# MultipleFiles/fov.py
import math

class FOV:
    def __init__(self, game_map):
        self.game_map = game_map
        self.visible_sources = {}
        self.explored = set()
    
    def compute_fov(self, origin_x, origin_y, radius=8, light_source_type='player', player_darkvision_radius=0):
        """Compute field of view from origin point using simple raycasting"""
        
        # Adjust radius if player has darkvision and it's the player's light source
        # If player_darkvision_radius is greater than the base radius, use it.
        if light_source_type == 'player' and player_darkvision_radius > radius:
            radius = player_darkvision_radius # Use the extended darkvision radius
        
        # Origin is always visible
        self.visible_sources[(origin_x, origin_y)] = light_source_type
        self.explored.add((origin_x, origin_y))
        
        # Cast rays in all directions
        # Pass player_darkvision_radius to _cast_ray as well, so it can tint correctly
        for angle in range(0, 360, 2):
            self._cast_ray(origin_x, origin_y, angle, radius, light_source_type, player_darkvision_radius)
    

    def _cast_ray(self, start_x, start_y, angle, max_distance, light_source_type, player_darkvision_radius=0):
        """Cast a ray from start position at given angle"""
        rad = math.radians(angle)
        dx = math.cos(rad)
        dy = math.sin(rad)
        
        for i in range(max_distance + 1):
            x = int(start_x + dx * i)
            y = int(start_y + dy * i)
            
            if not (0 <= x < self.game_map.width and 0 <= y < self.game_map.height):
                break
            
            current_source = self.visible_sources.get((x, y))
            
            # CORRECTED LOGIC FOR DARKVISION TINTING
            if light_source_type == 'player':
                # If this ray is from the player's light source
                # If darkvision is active and we are beyond the normal sight range (8)
                if player_darkvision_radius > 0 and i > 6: 
                    # This tile is visible due to darkvision, so it's dim
                    if current_source != 'player': # Don't overwrite full player light if it's already set
                        self.visible_sources[(x, y)] = 'darkvision' # 'darkvision' source type
                elif current_source != 'player': # If not darkvision extended, and not already player light
                    self.visible_sources[(x, y)] = 'player' # Set to full player light
            elif current_source == 'player':
                pass # Player light always takes precedence, don't downgrade
            elif current_source == 'torch' and light_source_type == 'player':
                self.visible_sources[(x, y)] = 'player' # Upgrade to player light
            else: # No source, or current source is 'torch' and new source is 'torch'
                self.visible_sources[(x, y)] = light_source_type

            self.explored.add((x, y))
            
            if self.game_map.tiles[y][x].block_sight:
                break


    # NEW: Update get_visibility_type to handle 'darkvision'
    def get_visibility_type(self, x, y):
        """Returns 'player', 'torch', 'darkvision', 'explored', or 'unexplored'"""
        if (x, y) in self.visible_sources:
            return self.visible_sources[(x, y)]
        elif (x, y) in self.explored:
            return 'explored'
        return 'unexplored'

