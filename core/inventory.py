class Inventory:
    def __init__(self, capacity):
        self.capacity = capacity
        self.items = []

    def add_item(self, item):
        if len(self.items) >= self.capacity:
            return False # Inventory is full
        self.items.append(item)
        item.owner = self.owner # Set the item's owner (e.g., the player)
        return True

    def remove_item(self, item):
        if item in self.items:
            self.items.remove(item)
            item.owner = None
            return True
        return False

    def get_items_by_type(self, item_type):
        """Returns a list of items of a specific type (e.g., Potion, Weapon)."""
        return [item for item in self.items if isinstance(item, item_type)]
