import math

class FOV:
    def __init__(self, game_map, radius=4):
        self.game_map = game_map
        self.visible_sources = {}
        self.explored = set()
        self.radius = radius

    def compute_fov(self, origin_x, origin_y, radius=4, light_source_type='player', player_darkvision_radius=0):
        """
        Compute field of view from origin point using ray casting.
        Supports extended darkvision radius with smooth transition.
        """
        # Adjust radius if player has darkvision and it's the player's light source
        if light_source_type == 'player' and player_darkvision_radius > radius:
            # Use given radius as normal vision radius
            normal_radius = radius
            # Use player_darkvision_radius as extended radius
            extended_radius = player_darkvision_radius
        else:
            normal_radius = radius
            extended_radius = radius

        # Origin is always visible as 'player' light source
        self.visible_sources[(origin_x, origin_y)] = light_source_type
        self.explored.add((origin_x, origin_y))

        # Cast rays in all directions (every 2 degrees for smoothness)
        for angle in range(0, 360, 2):
            self._cast_ray(origin_x, origin_y, angle, normal_radius, light_source_type, extended_radius)

    def _cast_ray(self, start_x, start_y, angle, normal_radius, light_source_type, extended_radius):
        """
        Cast a ray from start position at given angle.
        Marks tiles within normal_radius as 'player' and tiles beyond up to extended_radius as 'darkvision'.
        Stops if a tile blocks sight.
        """
        rad = math.radians(angle)
        dx = math.cos(rad)
        dy = math.sin(rad)

        for i in range(extended_radius + 1):  # Cast up to extended radius (darkvision)
            x = int(start_x + dx * i)
            y = int(start_y + dy * i)

            if not (0 <= x < self.game_map.width and 0 <= y < self.game_map.height):
                break

            current_source = self.visible_sources.get((x, y))

            if light_source_type == 'player':
                if i <= normal_radius:
                    # Within normal vision radius: full light
                    self.visible_sources[(x, y)] = 'player'
                else:
                    # Beyond normal radius but within darkvision radius: dim light
                    if current_source != 'player':  # Don't overwrite full player light
                        self.visible_sources[(x, y)] = 'darkvision'
            else:
                # For other light sources (e.g., torch), just set normally
                self.visible_sources[(x, y)] = light_source_type

            self.explored.add((x, y))

            # Stop ray if tile blocks sight
            if self.game_map.tiles[y][x].block_sight:
                break

    def get_visibility_type(self, x, y):
        """
        Returns the visibility type of the tile at (x, y).
        Possible values: 'player', 'torch', 'darkvision', 'explored', 'unexplored'.
        """
        if (x, y) in self.visible_sources:
            return self.visible_sources[(x, y)]
        elif (x, y) in self.explored:
            return 'explored'
        return 'unexplored'

    def is_within_chebyshev_distance(self, x1, y1, x2, y2, max_distance):
        """
        Check if the target is within Chebyshev distance.
        """
        return max(abs(x1 - x2), abs(y1 - y2)) <= max_distance
