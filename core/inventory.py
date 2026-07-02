class Inventory:
    def __init__(self, capacity):
        self.capacity = capacity
        self.items = []
        self.game_instance = None  # Set by the game after player creation

    def add_item(self, item):
        if len(self.items) >= self.capacity:
            return False  # Inventory is full
        self.items.append(item)
        item.owner = self.owner  # Set the item's owner (e.g., the player)

        # After adding, auto-fill any empty quick bar slots that match this item
        if self.game_instance and hasattr(self.owner, 'quick_bar'):
            for slot_key, slot_item in self.owner.quick_bar.items():
                if slot_item is None:
                    self.owner._auto_refill_quick_bar_slot(slot_key, self.game_instance)

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

    def get_equipped_items(self):
        """Returns a tuple of equipped weapon, armor, and off-hand item."""
        return self.equipped_weapon, self.equipped_armor, self.equipped_off_hand


    def reset_selected_index(self):
        """Reset the selected inventory index to a valid position."""
        if self.items:
            self.selected_inventory_index = min(self.selected_inventory_index, len(self.items) - 1)
        else:
            self.selected_inventory_index = 0  # Reset to 0 if no items