import heapq

class Node:
    """A node in the pathfinding grid."""
    def __init__(self, parent=None, position=None):
        self.parent = parent
        self.position = position

        self.g = 0  # Cost from start to this node
        self.h = 0  # Heuristic (estimated cost from this node to end)
        self.f = 0  # Total cost (g + h)

    def __eq__(self, other):
        return self.position == other.position

    def __hash__(self):
        return hash(self.position)

    # For heapq (priority queue)
    def __lt__(self, other):
        return self.f < other.f

def astar(game_map, start, end, entities=None):
    """
    Returns a list of tuples as a path from the given start to the given end in the given game_map.
    :param game_map: The GameMap object.
    :param start: A tuple (x, y) representing the start coordinates.
    :param end: A tuple (x, y) representing the end coordinates.
    :param entities: A list of entities to consider as obstacles (e.g., other monsters).
    :return: A list of (x, y) tuples representing the path, or None if no path found.
    """
    # Create start and end node
    start_node = Node(None, start)
    end_node = Node(None, end)

    # Initialize open and closed lists
    open_list = [] # Priority queue (heap)
    closed_list = set()

    # Add the start node
    heapq.heappush(open_list, start_node)

    # Loop until the open list is empty
    while open_list:
        # Get the current node (node with the lowest f-cost)
        current_node = heapq.heappop(open_list)
        closed_list.add(current_node.position)

        # Found the goal
        if current_node.position == end_node.position:
            path = []
            current = current_node
            while current is not None:
                path.append(current.position)
                current = current.parent
            return path[::-1] # Return reversed path

        # Generate children
        # Adjacent squares (8 directions)
        for new_position in [(0, -1), (0, 1), (-1, 0), (1, 0), (-1, -1), (-1, 1), (1, -1), (1, 1)]:
            node_position = (current_node.position[0] + new_position[0], current_node.position[1] + new_position[1])

            # Make sure within map bounds
            if not (0 <= node_position[0] < game_map.width and 0 <= node_position[1] < game_map.height):
                continue

            # Make sure walkable terrain
            if not game_map.is_walkable(node_position[0], node_position[1]):
                continue

            # Make sure not blocked by another entity (excluding the current entity and the target)
            if entities:
                is_blocked_by_entity = False
                for entity in entities:
                    # Don't block if the entity is the start or end of the path
                    if entity.x == node_position[0] and entity.y == node_position[1] and \
                       (node_position != start) and (node_position != end):
                        is_blocked_by_entity = True
                        break
                if is_blocked_by_entity:
                    continue

            # Create new node
            new_node = Node(current_node, node_position)

            # Check if already in the closed list
            if new_node.position in closed_list:
                continue

            # Calculate f, g, and h values
            new_node.g = current_node.g + 1 # Cost to move to adjacent square
            # Heuristic: Manhattan distance (can use Euclidean for more accurate but slower)
            new_node.h = abs(new_node.position[0] - end_node.position[0]) + abs(new_node.position[1] - end_node.position[1])
            new_node.f = new_node.g + new_node.h

            # Check if node is already in open list with a lower f-cost
            # This part is crucial for efficiency with heapq
            found_in_open = False
            for open_node in open_list:
                if new_node == open_node and new_node.g >= open_node.g:
                    found_in_open = True
                    break
            
            if not found_in_open:
                heapq.heappush(open_list, new_node)

    return None # No path found
