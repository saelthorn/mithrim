# MultipleFiles/items/items.py

import random # Add this import for potential random loot generation later

class Item:
    """Base class for all items."""
    def __init__(self, name, char, color, description=""):
        self.name = name
        self.char = char
        self.color = color
        self.description = description
        self.owner = None # The entity that owns this item
        self.x = -1 # Default invalid position
        self.y = -1 # Default invalid position

    def __str__(self):
        return self.name

    def on_pickup(self, picker, game_instance):
        """Called when the item is picked up."""
        game_instance.message_log.add_message(f"You pick up the {self.name}.", self.color)
        picker.inventory.add_item(self)
        # Remove from map if it was on the ground
        if self in game_instance.game_map.items_on_ground:
            game_instance.game_map.items_on_ground.remove(self)

    def on_drop(self, dropper, game_instance):
        """Called when the item is dropped."""
        game_instance.message_log.add_message(f"You drop the {self.name}.", self.color)
        dropper.inventory.remove_item(self)
        # Place on map at dropper's position
        self.x = dropper.x
        self.y = dropper.y
        game_instance.game_map.items_on_ground.append(self)

class Potion(Item):
    """A consumable item that provides an effect."""
    def __init__(self, name, char, color, description, effect_type, effect_value):
        super().__init__(name, char, color, description)
        self.effect_type = effect_type
        self.effect_value = effect_value

    def use(self, user, game_instance):
        """Apply the potion's effect to the user."""
        if self.effect_type == "heal":
            amount_healed = user.heal(self.effect_value)
            game_instance.message_log.add_message(f"You drink the {self.name} and heal for {amount_healed} HP!", (0, 255, 0))
        # Add other effect types here (e.g., "strength_boost", "poison_cure")
        
        user.inventory.remove_item(self) # Remove after use
        game_instance.message_log.add_message(f"The {self.name} is consumed.", (150, 150, 150))

class Weapon(Item):
    """An item that can be equipped for combat."""
    def __init__(self, name, char, color, description, damage_dice, damage_modifier, attack_bonus=0):
        super().__init__(name, char, color, description)
        self.damage_dice = damage_dice # e.g., "1d6", "2d4"
        self.damage_modifier = damage_modifier
        self.attack_bonus = attack_bonus # Bonus to hit

class Armor(Item):
    """An item that can be equipped for defense."""
    def __init__(self, name, char, color, description, ac_bonus):
        super().__init__(name, char, color, description)
        self.ac_bonus = ac_bonus # Bonus to AC

# --- NEW CHEST CLASS ---
class Chest(Item):
    def __init__(self, x, y, contents=None):
        super().__init__("Chest", 'C', (139, 69, 19), "A sturdy wooden chest.")
        self.x = x
        self.y = y
        self.opened = False
        self.contents = contents if contents is not None else [] # List of Item objects

    def open(self, opener, game_instance):
        """Opens the chest and transfers its contents to the opener's inventory."""
        if self.opened:
            game_instance.message_log.add_message("This chest is already empty.", (150, 150, 150))
            return

        game_instance.message_log.add_message("You open the chest...", (255, 215, 0))
        self.opened = True
        self.char = 'c' # Change appearance to open chest

        if not self.contents:
            game_instance.message_log.add_message("It's empty!", (150, 150, 150))
            return

        items_given = []
        for item in list(self.contents): # Iterate over a copy as we modify the list
            if opener.inventory.add_item(item):
                items_given.append(item.name)
                self.contents.remove(item) # Remove from chest's contents
            else:
                game_instance.message_log.add_message(f"Your inventory is full! You couldn't pick up the {item.name}.", (255, 0, 0))
                # Leave item in chest if inventory is full

        if items_given:
            game_instance.message_log.add_message(f"You found: {', '.join(items_given)}!", (0, 255, 0))
        else:
            game_instance.message_log.add_message("Your inventory is full, you couldn't take anything.", (255, 0, 0))

# --- Pre-defined Items (Examples) ---
healing_potion = Potion(
    name="Healing Potion",
    char="!",
    color=(255, 0, 0),
    description="Restores a small amount of health.",
    effect_type="heal",
    effect_value=8 # Heals 8 HP
)

short_sword = Weapon(
    name="Short Sword",
    char="/",
    color=(150, 150, 150),
    description="A basic short sword.",
    damage_dice="1d6",
    damage_modifier=0,
    attack_bonus=0
)

leather_armor = Armor(
    name="Leather Armor",
    char="[",
    color=(139, 69, 19),
    description="Light leather armor.",
    ac_bonus=1 # Adds 1 to base AC
)

# Example function to create random loot for a chest
def generate_random_loot(level_number):
    loot = []
    # Basic loot pool
    loot_pool = [healing_potion, short_sword, leather_armor]

    # Add 1-3 random items
    num_items = random.randint(1, 3)
    for _ in range(num_items):
        chosen_item_template = random.choice(loot_pool)
        # Create a new instance of the item
        new_item = chosen_item_template.__class__(
            name=chosen_item_template.name,
            char=chosen_item_template.char,
            color=chosen_item_template.color,
            description=chosen_item_template.description,
            **{k: v for k, v in chosen_item_template.__dict__.items() if k not in ['name', 'char', 'color', 'description', 'owner', 'x', 'y']}
        )
        loot.append(new_item)
    return loot
