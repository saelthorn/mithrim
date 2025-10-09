import heapq
from world.water_features import is_water_tile

class Node:
    __slots__ = ('parent', 'position', 'g', 'h', 'f')  # reduces memory + lookup cost

    def __init__(self, parent=None, position=None):
        self.parent = parent
        self.position = position
        self.g = 0
        self.h = 0
        self.f = 0

    def __lt__(self, other):
        return self.f < other.f


def astar(game_map, start, end, entities=None, moving_entity=None, ignore_destructible=False):
    footprint_size = getattr(moving_entity, 'footprint_size', 1) if moving_entity else 1
    can_swim = getattr(moving_entity, 'can_swim', False)

    # Precompute entity blocked positions for O(1) lookup
    blocked_tiles = set()
    if entities:
        for ent in entities:
            if hasattr(ent, 'occupies_tile'):
                blocked_tiles.update(ent.occupies_tile(x, y) for x in range(game_map.width) for y in range(game_map.height) if ent.occupies_tile(x, y))
            else:
                if hasattr(ent, 'x') and hasattr(ent, 'y'):
                    blocked_tiles.add((ent.x, ent.y))
    blocked_tiles.discard(start)
    blocked_tiles.discard(end)

    def has_footprint_clearance(x, y) -> bool:
        """Efficient multi-tile footprint clearance check."""
        for oy in range(footprint_size):
            for ox in range(footprint_size):
                tx, ty = x + ox, y + oy
                if not (0 <= tx < game_map.width and 0 <= ty < game_map.height):
                    return False
                tile = game_map.tiles[ty][tx]
                if is_water_tile(tile):
                    if not can_swim:
                        return False
                elif not game_map.is_walkable(tx, ty):
                    return False
                if (tx, ty) in blocked_tiles and (tx, ty) != end:
                    return False
        return True

    open_heap = []
    open_dict = {}  # position -> Node for fast lookup
    closed_set = set()

    start_node = Node(None, start)
    heapq.heappush(open_heap, start_node)
    open_dict[start] = start_node

    neighbor_steps = [(0, -1), (0, 1), (-1, 0), (1, 0),
                      (-1, -1), (-1, 1), (1, -1), (1, 1)]

    while open_heap:
        current_node = heapq.heappop(open_heap)
        current_pos = current_node.position
        closed_set.add(current_pos)
        open_dict.pop(current_pos, None)

        if current_pos == end:
            path = []
            while current_node:
                path.append(current_node.position)
                current_node = current_node.parent
            return path[::-1]

        for dx, dy in neighbor_steps:
            nx, ny = current_pos[0] + dx, current_pos[1] + dy
            if not (0 <= nx < game_map.width and 0 <= ny < game_map.height):
                continue

            neighbor_pos = (nx, ny)
            if neighbor_pos in closed_set:
                continue

            tile = game_map.tiles[ny][nx]
            is_tile_water = is_water_tile(tile)
            is_walkable = game_map.is_walkable(nx, ny)

            if is_tile_water:
                if not can_swim:
                    continue
            elif not is_walkable:
                if not (ignore_destructible and getattr(tile, 'destructible', False) and footprint_size >= 3):
                    continue

            if footprint_size > 1 and not has_footprint_clearance(nx, ny):
                continue
            elif footprint_size == 1 and (neighbor_pos in blocked_tiles):
                continue

            g_cost = current_node.g + 1
            h_cost = abs(nx - end[0]) + abs(ny - end[1])
            f_cost = g_cost + h_cost

            # Faster open node check
            existing = open_dict.get(neighbor_pos)
            if existing and g_cost >= existing.g:
                continue

            new_node = Node(current_node, neighbor_pos)
            new_node.g, new_node.h, new_node.f = g_cost, h_cost, f_cost
            heapq.heappush(open_heap, new_node)
            open_dict[neighbor_pos] = new_node

    return None
