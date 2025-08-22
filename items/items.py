import random

from core.game import GameState


class Item:
    """Base class for all items."""
    def __init__(self, name, char, color, description="", price=10):
        self.name = name
        self.char = char
        self.color = color
        self.description = description
        self.price = price
        self.owner = None # The entity that owns this item
        self.x = -1 # Default invalid position
        self.y = -1 # Default invalid position

    def __str__(self):
        return self.name

    def on_pickup(self, picker, game_instance):
        """Handle the logic for picking up the item."""
        # Prevent picking up chests or other non-pickupable items
        if isinstance(self, Chest):  # Assuming you have a Chest class
            game_instance.message_log.add_message(f"You cannot pick up the {self.name}. It's too heavy!", (255, 0, 0))
            return False
        
        # Add the item to the picker's inventory
        if picker.inventory.add_item(self):
            self.owner = picker  # Set the owner of the item
            game_instance.message_log.add_message(f"{picker.name} picks up the {self.name}.", (0, 255, 0))
            return True
        else:
            game_instance.message_log.add_message(f"{picker.name}'s inventory is full!", (255, 0, 0))
            return False
        
    def on_drop(self, dropper, game_instance):
        """Called when the item is dropped."""
        game_instance.message_log.add_message(f"You drop the {self.name}.", self.color)
        dropper.inventory.remove_item(self)
        # Place on map at dropper's position
        self.x = dropper.x
        self.y = dropper.y
        game_instance.game_map.items_on_ground.append(self)
        game_instance.update_fov() # Update FOV to show dropped item


class Potion(Item):
    """A consumable item that provides an effect."""
    def __init__(self, name, char, color, description, effect_type, effect_value, price):
        super().__init__(name, char, color, description, price)
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
    def __init__(self, name, char, color, description, damage_dice, damage_modifier, price, attack_bonus=0):
        super().__init__(name, char, color, description, price)
        self.damage_dice = damage_dice # e.g., "1d6", "2d4"
        self.damage_modifier = damage_modifier
        self.attack_bonus = attack_bonus # Bonus to hit


class Armor(Item):
    """An item that can be equipped for defense."""
    def __init__(self, name, char, color, description, ac_bonus, price):
        super().__init__(name, char, color, description, price)
        self.ac_bonus = ac_bonus # Bonus to AC


class Tools(Item):
    """An item that can be used in certain situations"""
    def __init__(self, name, char, color, price, description=""):
        super().__init__(name, char, color, description, price)

class Junk(Item):
    """A useless piece of wood."""
    def __init__(self, name, char, color, description=""):
        super().__init__(name, char, color, description)


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
        self.char = 'O' # <--- CHANGE THIS LINE to the new character for open chest
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

    def on_pickup(self, picker, game_instance):
        """Handle the logic for picking up the chest."""
        game_instance.message_log.add_message(f"You cannot pick up the {self.name}. It's too heavy!", (255, 0, 0))
        return False  # Prevent pickup            

class CampfireKit(Item):
    def __init__(self):
        super().__init__(name="Campfire Kit", char="cf", color=(255, 140, 0), description="A kit to set up a campfire.", price=15)
        self.uses_left = 3  # Number of uses for the campfire kit

    def use(self, user, game_instance):
        """Use the campfire kit to drop it at the player's position and emit light."""
        if self.uses_left > 0:
            # Close the inventory menu if it's open
            if game_instance.game_state in [GameState.INVENTORY, GameState.INVENTORY_MENU]:
                game_instance.message_log.add_message("Closing inventory to drop the campfire kit.", (150, 150, 150))
                game_instance.selected_inventory_item = None  # Reset selected item

            # Drop the campfire kit at the player's position
            self.x = user.x  # Set the x position to the player's x
            self.y = user.y  # Set the y position to the player's y
            game_instance.game_map.items_on_ground.append(self)  # Add the campfire kit to the ground items

            game_instance.message_log.add_message(f"{user.name} sets down a campfire kit!", (0, 255, 0))
            self.uses_left -= 1  # Decrease the number of uses left
            game_instance.player.inventory.remove_item(self)  # Remove the campfire kit from the player's inventory
            
            # Check if the campfire kit has no uses left
            if self.uses_left <= 0:
                game_instance.message_log.add_message(f"The Campfire Kit has broken and is no longer usable.", (255, 0, 0))
                user.inventory.remove_item(self)  # Remove the campfire kit from the player's inventory
            
            return True
        else:
            game_instance.message_log.add_message("The Campfire Kit has no uses left.", (255, 0, 0))
            return False

    


# --- Junk Items ---
wood_plank = Junk(
    name="Plank",
    char="pn",
    color=(139, 69, 19),
    description="Just a useless piece of wood."
)


# --- Pre-defined Items (Examples) ---
lesser_healing_potion = Potion(
    name="Lesser Healing Potion",
    char="!",
    color=(255, 80, 80),
    description="Restores a small amount of health.",
    effect_type="heal",
    effect_value=8, # Heals 8 HP
    price = 10
)

greater_healing_potion = Potion(
    name="Greater Healing Potion",
    char="!",
    color=(240, 0, 0),
    description="Restores a great amount of health.",
    effect_type="heal",
    effect_value=24,
    price = 10
)

dagger = Weapon(
    name="Dagger",
    char="-", # Using same char as other weapons for now
    color=(180, 180, 180),
    description="A small, light blade.",
    damage_dice="1d4",
    damage_modifier=0,
    attack_bonus=0,
    price = 10
)

short_sword = Weapon(
    name="Short Sword",
    char="/",
    color=(150, 150, 150),
    description="A basic short sword.",
    damage_dice="1d6",
    damage_modifier=0,
    attack_bonus=0,
    price = 10
)

long_sword = Weapon(
    name="Long Sword",
    char="|",
    color=(150, 150, 150),
    description="A adventurer's sword.",
    damage_dice="1d6",
    damage_modifier=1,
    attack_bonus=2,
    price = 10
)

battle_axe = Weapon(
    name="Battle Axe",
    char="?",
    color=(150, 150, 150),
    description="A battle tested axe.",
    damage_dice="1d8",
    damage_modifier=1,
    attack_bonus=0,
    price = 10
)

quarterstaff = Weapon(
    name="Quarterstaff",
    char="l",
    color=(150, 150, 150),
    description="A sturdy wooden staff.",
    damage_dice="1d6",
    damage_modifier=0,
    attack_bonus=0,
    price = 10
)

leather_armor = Armor(
    name="Leather Armor",
    char="lta",
    color=(139, 69, 19),
    description="Light leather armor.",
    ac_bonus=1, # Adds 1 to base AC
    price = 10
)

chainmail_armor = Armor(
    name="Chainmail Armor",
    char="cha",
    color=(175, 175, 175),
    description="Chainmail armor.",
    ac_bonus=3, # Adds 1 to base AC
    price = 10
)

robes = Armor(
    name="Robes",
    char="rbs", # Using same char as other armor for now
    color=(100, 100, 200),
    description="Simple cloth robes.",
    ac_bonus=0, # Robes typically provide no AC bonus, relying on Dex
    price = 10
)

thieves_tools = Tools(
    name="Thieves' Tools",
    char="tt",
    color=(255, 215, 0),
    description="Tools to unlock/disable trinkets",
    price = 10
)


# Example function to create random loot for a chest
def generate_random_loot(level_number):
    loot = []
    # Basic loot pool
    loot_pool = [lesser_healing_potion, greater_healing_potion, dagger, short_sword, long_sword, quarterstaff, battle_axe, leather_armor, chainmail_armor]

    # Add 1-3 random items
    num_items = random.randint(1, 2)
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
