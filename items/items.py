# MultipleFiles/items.py

class Item:
    """Base class for all items."""
    def __init__(self, name, char, color, description=""):
        self.name = name
        self.char = char
        self.color = color
        self.description = description
        self.owner = None # The entity that owns this item

    def __str__(self):
        return self.name

    def on_pickup(self, picker, game_instance):
        """Called when the item is picked up."""
        game_instance.message_log.add_message(f"You pick up the {self.name}.", self.color)
        # Item is added to inventory in game.handle_item_pickup, not here
        # picker.inventory.add_item(self) # This line is redundant if handled in game.py
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

    def use(self, user, game_instance):
        """Default use method for items. Should be overridden by subclasses."""
        game_instance.message_log.add_message(f"You can't use the {self.name} this way.", (255, 100, 100))
        return False

    def equip(self, user, game_instance):
        """Default equip method for items. Should be overridden by subclasses."""
        game_instance.message_log.add_message(f"You can't equip the {self.name}.", (255, 100, 100))
        return False


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
            if amount_healed > 0: # Only consume if actually healed
                game_instance.message_log.add_message(f"You drink the {self.name} and heal for {amount_healed} HP!", (0, 255, 0))
                user.inventory.remove_item(self) # Remove after use
                game_instance.message_log.add_message(f"The {self.name} is consumed.", (150, 150, 150))
                return True
            else:
                game_instance.message_log.add_message(f"You are already at full health.", (150, 150, 150))
                return False
        # Add other effect types here (e.g., "strength_boost", "poison_cure")
        return False # If effect type not handled

class Weapon(Item):
    """An item that can be equipped for combat."""
    def __init__(self, name, char, color, description, damage_dice, damage_modifier, attack_bonus=0):
        super().__init__(name, char, color, description)
        self.damage_dice = damage_dice # e.g., "1d6", "2d4"
        self.damage_modifier = damage_modifier
        self.attack_bonus = attack_bonus # Bonus to hit

    def equip(self, user, game_instance):
        return user.equip_item(self, game_instance)

class Armor(Item):
    """An item that can be equipped for defense."""
    def __init__(self, name, char, color, description, ac_bonus):
        super().__init__(name, char, color, description)
        self.ac_bonus = ac_bonus # Bonus to AC

    def equip(self, user, game_instance):
        return user.equip_item(self, game_instance)

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
