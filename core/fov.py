import math

class FOV:
    def __init__(self, game_map, radius=4):
        self.game_map = game_map
        self.visible_sources = {}
        self.explored = set()
        self.radius = radius

    def compute_fov(self, origin_x, origin_y, radius=4, light_source_type='player', player_darkvision_radius=0):
        if light_source_type == 'player' and player_darkvision_radius > radius:
            normal_radius = radius
            extended_radius = player_darkvision_radius
        else:
            normal_radius = radius
            extended_radius = radius

        self.visible_sources[(origin_x, origin_y)] = light_source_type
        self.explored.add((origin_x, origin_y))

        # OPTIMIZATION: Use squared distances to avoid sqrt in tight loop
        extended_radius_sq = extended_radius * extended_radius
        normal_radius_sq = normal_radius * normal_radius

        # Cast a ray toward every tile within the extended radius bounding box
        for ty in range(origin_y - extended_radius, origin_y + extended_radius + 1):
            for tx in range(origin_x - extended_radius, origin_x + extended_radius + 1):
                # Skip origin (already added above)
                if tx == origin_x and ty == origin_y:
                    continue

                # OPTIMIZATION: Use squared distance comparison to avoid sqrt
                dist_sq = (tx - origin_x) ** 2 + (ty - origin_y) ** 2
                if dist_sq > extended_radius_sq:
                    continue

                # Only compute sqrt when needed
                dist = math.sqrt(dist_sq)
                self._cast_ray_to_tile(
                    origin_x, origin_y,
                    tx, ty,
                    dist, normal_radius, normal_radius_sq,
                    light_source_type
                )

    def _cast_ray_to_tile(self, start_x, start_y, target_x, target_y, target_dist, normal_radius, normal_radius_sq, light_source_type):
        """
        Cast a ray from origin toward a specific target tile.
        Steps along the ray in 0.5-unit increments to avoid skipping
        narrow walls, stopping if a sight-blocking tile is hit.
        
        OPTIMIZED: Uses squared distances for tile distance comparison
        """
        dx = target_x - start_x
        dy = target_y - start_y
        length = math.sqrt(dx * dx + dy * dy)
        step_x = dx / length
        step_y = dy / length

        step_size = 0.5
        steps = int(length / step_size) + 1

        seen_tiles = set()

        for i in range(1, steps + 1):
            dist = i * step_size
            if dist > length + step_size:
                break

            x = int(round(start_x + step_x * dist))
            y = int(round(start_y + step_y * dist))

            if not (0 <= x < self.game_map.width and 0 <= y < self.game_map.height):
                break

            if (x, y) in seen_tiles:
                continue
            seen_tiles.add((x, y))

            # OPTIMIZATION: Use squared distance to avoid sqrt
            tile_dist_sq = (x - start_x) ** 2 + (y - start_y) ** 2

            current_source = self.visible_sources.get((x, y))

            if light_source_type == 'player':
                # Compare squared distances (no sqrt needed)
                if tile_dist_sq <= normal_radius_sq:
                    self.visible_sources[(x, y)] = 'player'
                else:
                    if current_source != 'player':
                        self.visible_sources[(x, y)] = 'darkvision'
            else:
                self.visible_sources[(x, y)] = light_source_type

            self.explored.add((x, y))

            # Stop the ray if this tile blocks sight
            if self.game_map.tiles[y][x].block_sight:
                break

    def get_visibility_type(self, x, y):
        if (x, y) in self.visible_sources:
            return self.visible_sources[(x, y)]
        elif (x, y) in self.explored:
            return 'explored'
        return 'unexplored'

    def is_within_chebyshev_distance(self, x1, y1, x2, y2, max_distance):
        return max(abs(x1 - x2), abs(y1 - y2)) <= max_distance