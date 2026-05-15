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
        if self.name.lower() == "torch":
            self.remaining_torchlight_duration = 0        

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
        return True


class Food(Item):
    def __init__(self, name, char, color, description, healing_value, price=0):
        super().__init__(name, char, color, description, price)
        self.healing_value = healing_value # Amount of hunger restored

    def use(self, user, game_instance):
        """This method will be called by Player.use_item, but the actual hunger logic is in Player.eat_food."""
        return True # Indicate that it's a usable item type        



class Weapon(Item):
    """An item that can be equipped for combat."""
    def __init__(self, name, char, color, description, damage_dice, damage_modifier, price, attack_bonus=0, spell_bonus=0, is_two_handed=False, category=None):
        super().__init__(name, char, color, description, price)
        self.damage_dice = damage_dice # e.g., "1d6", "2d4"
        self.damage_modifier = damage_modifier
        self.attack_bonus = attack_bonus # Bonus to hit
        self.spell_bonus = spell_bonus
        self.is_two_handed = is_two_handed
        self.category = category


class Armor(Item):
    """An item that can be equipped for defense."""
    def __init__(self, name, char, color, description, ac_bonus, price, category=None):
        super().__init__(name, char, color, description, price)
        self.ac_bonus = ac_bonus # Bonus to AC
        self.category = category

class OffHand(Item):
    def __init__(self, name, char, color, description, price, defense_bonus=0, attack_bonus=0, spell_bonus=0, damage_dice=None, damage_modifier=0, category=None, remaining_duration=250):
        super().__init__(name, char, color, description, price)
        self.defense_bonus = defense_bonus  # Bonus to armor class if it's a shield
        self.attack_bonus = attack_bonus  # Bonus to attack rolls if it's a weapon
        self.spell_bonus = spell_bonus  # Bonus to spell attacks if it's a magic item
        self.damage_dice = damage_dice  # Damage dice for one-handed weapons (e.g., "1d6")
        self.damage_modifier = damage_modifier  # Additional damage modifier
        self.category = category
        self.remaining_duration = remaining_duration # For items like torch that have limited duration when equipped

    def use(self, user, game_instance):
        """Define how the item is used, if applicable."""
        # Implement specific use logic for off-hand items if needed
        pass

class Accessory(Item):
    def __init__(self, name, char, color, description, price, ac_bonus=0, attack_bonus=0, damage_bonus=0, hp_bonus=0, skill_bonus=None, category=None):
        super().__init__(name, char, color, description, price)
        self.ac_bonus = ac_bonus  # Bonus to armor class
        self.attack_bonus = attack_bonus  # Bonus to attack rolls
        self.damage_bonus = damage_bonus  # Bonus to damage
        self.hp_bonus = hp_bonus  # Bonus to max HP
        self.skill_bonus = skill_bonus  # Dict like {"investigation": 2} for skill bonuses
        self.category = category

    def use(self, user, game_instance):
        """Define how the item is used, if applicable."""
        pass

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
        super().__init__(name="Campfire Kit", char="cf", color=(255, 140, 0), description="A kit to set up a campfire.", price=25)
        self.uses_left = 5  # Number of uses for the campfire kit

    def use(self, user, game_instance):
        """Use the campfire kit to drop it at the player's position and emit light."""
        if self.uses_left > 0:
            
            if game_instance.game_state in [GameState.INVENTORY, GameState.INVENTORY_MENU, GameState.DUNGEON]:
                game_instance.message_log.add_message("Closing inventory to drop the campfire kit.", (150, 150, 150))
                game_instance.selected_inventory_item = None  # Reset selected item

            self.x = user.x  # Set the x position to the player's x
            self.y = user.y  # Set the y position to the player's y
            game_instance.game_map.items_on_ground.append(self)  

            game_instance.message_log.add_message(f"{user.name} sets down a campfire kit!", (0, 255, 0))
            self.uses_left -= 1  # Decrease the number of uses left
            game_instance.player.inventory.remove_item(self)  
            
            if self.uses_left <= 0:
                game_instance.message_log.add_message(f"The Campfire Kit has broken and is no longer usable.", (255, 0, 0))
                user.inventory.remove_item(self)  
            
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
    effect_value=10, # Heals 8 HP
    price = 10
)

greater_healing_potion = Potion(
    name="Greater Healing Potion",
    char="!",
    color=(240, 0, 0),
    description="Restores a great amount of health.",
    effect_type="heal",
    effect_value=24,
    price = 20
)

meat = Food(
    name="Meat",
    description="A meat from unknown origin, chewy but full of taste.",
    healing_value=40,
    price=15,
    char="met",
    color=(255, 0, 0)
)

green_apple = Food(
    name="Green Apple",
    description="A fruit that has sweet and tarty taste.",
    healing_value=15,
    price=5,
    char="gra",
    color=(0, 255, 0)
)

fromage = Food(
    name="Fromage",
    description="Ce type de fromage est un peu salé et a une saveur umami.",
    healing_value=30,
    price=12,
    char="frg",
    color=(255, 255, 0)
)

bread = Food(
    name="Bread",
    description="Food that is often brought when crawling dungeons.",
    healing_value=25,
    price=8,
    char="brd",
    color=(200, 200, 100)
)

mushroom = Food(
    name="Mushroom",
    description="Food that is often found in dungeon, has a distinct earthy flavour.",
    healing_value=10,
    price=0,
    char="msm",
    color=(220, 220, 220)
)


WEAPON_CATEGORIES = {
    "dagger": ["Iron Dagger", "Silver Dagger"],
    "orb": ["Glass Orb", "Orb of Chaos"],
    "shortsword": ["Iron Short Sword", "Bronze Short Sword", "Flameheart Short Sword"],
    "longsword": ["Steel Long Sword", "Iron Long Sword", "Adamantine Long Sword"],
    "quarterstaff": ["Oak Staff", "Apprentice's Staff", "Staff of the Magi"],
    "battleaxe": ["Steel Battle Axe", "Dwarven Battle Axe"],
    "polearm": ["Polearm"],
    "rapier": ["Steel Rapier", "Duelists Rapier"],
    "hammer": ["Iron Hammer", "Dragonsbane Warhammer", "Steel Maul"],
    "mace": ["Steel Mace"],
    "flail": ["Dwarven Flail", "Flameheart Flail"],
}

torch = OffHand(
    name="Torch", 
    char='th', 
    color=(255, 140, 0), 
    description="A burning torch that can be held in your off-hand. Provides extra light.", 
    damage_modifier=1,
    attack_bonus=0,
    price=10,
    remaining_duration=250
)

throwing_knife = OffHand(
    name="Throwing Knife",
    char="thr", # Using same char as other weapons for now
    color=(180, 180, 180),
    description="A small knife designed for throwing.",
    damage_dice="1d4",
    damage_modifier=1,
    attack_bonus=2,
    price = 10,
    category="dagger"
)

spell_book = OffHand(
    name="Spell Book",
    char="spb",
    color=(120, 0, 220),
    description="A wizard's spell book that enables advanced spellcasting.",
    defense_bonus=0,
    attack_bonus=0,
    price=50,
    category="spellbook"
)

holy_symbol = Accessory(
    name="Holy Symbol",
    char="hsy",
    color=(255, 255, 0),
    description="A sacred symbol of great power.",
    ac_bonus=0,
    attack_bonus=0,
    price=40,
    category="holy_symbol",
)

iron_dagger = OffHand(
    name="Iron Dagger",
    char="dgr", # Using same char as other weapons for now
    color=(180, 180, 180),
    description="A small, light blade.",
    damage_dice="1d4",
    damage_modifier=2,
    attack_bonus=1,
    price = 15,
    category="dagger"
)

silver_dagger = OffHand(
    name="Silver Dagger",
    char="sdr", # Using same char as other weapons for now
    color=(180, 180, 180),
    description="A silver blade.",
    damage_dice="1d4",
    damage_modifier=3,
    attack_bonus=3,
    price = 30,
    category="dagger"
)

glass_orb = OffHand(
    name="Glass Orb",
    char="glo",
    color=(200, 200, 200),
    description="A glass orb.",
    damage_dice="1d4",
    damage_modifier=1,
    attack_bonus=1,
    price=20,
    category="orb"
)

orb_of_chaos = OffHand(
    name="Orb of Chaos",
    char="ooc",
    color=(200, 200, 200),
    description="An orb that brings chaos.",
    damage_dice="1d4",
    damage_modifier=2,
    attack_bonus=4,
    price=20,
    category="orb"
)

iron_short_sword = Weapon(
    name="Iron Short Sword",
    char="shs",
    color=(150, 150, 150),
    description="A basic short sword.",
    damage_dice="1d6",
    damage_modifier=0,
    attack_bonus=0,
    price = 10,
    category="shortsword"
)

flameheart_short_sword = Weapon(
    name="Flameheart Short Sword",
    char="fhs",
    color=(150, 150, 150),
    description="A short sword infused in fire magic.",
    damage_dice="1d6",
    damage_modifier=2,
    attack_bonus=2,
    price = 30,
    category="shortsword"
)

bronze_short_sword = Weapon(
    name="Bronze Short Sword",
    char="bss",
    color=(150, 150, 150),
    description="An old bronze shortsword.",
    damage_dice="1d6",
    damage_modifier=0,
    attack_bonus=0,
    price = 5,
    category="shortsword"
)


iron_long_sword = Weapon(
    name="Iron Long Sword",
    char="lns",
    color=(150, 150, 150),
    description="A adventurer's sword.",
    damage_dice="1d8",
    damage_modifier=0,
    attack_bonus=1,
    price = 15,
    category="longsword"
)

steel_long_sword = Weapon(
    name="Steel Long Sword",
    char="sls",
    color=(150, 150, 150),
    description="A steel longsword.",
    damage_dice="1d8",
    damage_modifier=1,
    attack_bonus=2,
    price = 25,
    category="longsword"
)

adamantine_long_sword = Weapon(
    name="Adamantine Long Sword",
    char="als",
    color=(150, 150, 150),
    description="A adamantine long sword.",
    damage_dice="1d8",
    damage_modifier=4,
    attack_bonus=2,
    price = 50,
    category="longsword"
)


steel_battle_axe = Weapon(
    name="Steel Battle Axe",
    char="sba",
    color=(150, 150, 150),
    description="Steel battle axe.",
    damage_dice="1d12",
    damage_modifier=1,
    attack_bonus=0,
    price = 15,
    category="battleaxe"
)

dwarven_battle_axe = Weapon(
    name="Dwarven Battle Axe",
    char="dba",
    color=(150, 150, 150),
    description="A dwarven battle tested axe.",
    damage_dice="1d12",
    damage_modifier=1,
    attack_bonus=3,
    price = 30,
    is_two_handed=True,
    category="battleaxe"
)

pole_arm = Weapon(
    name="Pole Arm",
    char="pla",
    color=(150, 150, 150),
    description="A battle tested axe.",
    damage_dice="1d10",
    damage_modifier=1,
    attack_bonus=2,
    price = 25,
    is_two_handed=True,
    category="polearm"
)

oak_staff = Weapon(
    name="Oak Staff",
    char="oas",
    color=(150, 150, 150),
    description="A sturdy wooden staff, doubles as arcane focus.",
    damage_dice="1d6",
    damage_modifier=0,
    attack_bonus=1,
    spell_bonus=1,
    price = 20,
    category="quarterstaff"
)

apprentices_staff = Weapon(
    name="Apprentice's Staff",
    char="aps",
    color=(150, 150, 150),
    description="A sturdy wooden staff, doubles as arcane focus.",
    damage_dice="1d6",
    damage_modifier=2,
    attack_bonus=1,
    spell_bonus=2,
    price = 30,
    category="quarterstaff"
)

staff_of_magi = Weapon(
    name="Staff of the Magi",
    char="som",
    color=(10, 10, 220),
    description="A staff of the magi.",
    damage_dice="1d6",
    damage_modifier=4,
    attack_bonus=1,
    spell_bonus=3,
    price = 50,
    category="quarterstaff"
)

steel_rapier = Weapon(
    name="Steel Rapier",
    char="srp",
    color=(175, 175, 175),
    description="Steel rapier.",
    damage_dice="1d8",
    damage_modifier=1,
    attack_bonus=0,
    price=20,
    category="rapier"
)

duelists_rapier = Weapon(
    name="Duelists Rapier",
    char="dlr",
    color=(175, 175, 175),
    description="A duelists rapier.",
    damage_dice="2d8",
    damage_modifier=2,
    attack_bonus=1,
    price=60,
    category="rapier"
)

iron_hammer = OffHand(
    name="Iron Hammer",
    char="irh",
    color=(175, 175, 175),
    description="A iron hammer.",
    damage_dice="1d8",
    damage_modifier=1,
    attack_bonus=0,
    price=15,
    category="hammer"
)

dragonsbane_warhammer = Weapon(
    name="Dragonsbane Warhammer",
    char="dbw",
    color=(175, 175, 175),
    description="A warhammer that has seen the end of countless dragons.",
    damage_dice="2d8",
    damage_modifier=4,
    attack_bonus=3,
    price=70,
    is_two_handed=True,
    category="hammer"
)

steel_maul = Weapon(
    name="Steel Maul",
    char="mul",
    color=(175, 175, 175),
    description="A steel maul.",
    damage_dice="2d6",
    damage_modifier=2,
    attack_bonus=1,
    price=30,
    is_two_handed=True,
    category="hammer"
)

steel_mace = Weapon(
    name="Steel Mace",
    char="stm",
    color=(200, 200, 200),
    description="A steel mace.",
    damage_dice="1d6",
    damage_modifier=1,
    attack_bonus=1,
    price=25,
    category="mace"
)

dwarven_flail = Weapon(
    name="Dwarven Flail",
    char="dwf",
    color=(200, 200, 200),
    description="A dwarven flail.",
    damage_dice="1d8",
    damage_modifier=2,
    attack_bonus=1,
    price=35,
    category="flail"
)

flameheart_flail = Weapon(
    name="Flameheart Flail",
    char="fhf",
    color=(200, 200, 200),
    description="A flameheart flail.",
    damage_dice="1d8",
    damage_modifier=4,
    attack_bonus=2,
    price=50,
    category="flail"
)





ARMOR_CATEGORIES = {
    "light": ["Padded Armor", "Studded Leather Armor", "Robes", "Robes of Protection"],
    "medium": ["Chainmail Armor", "Half Plate Armor"],
    "heavy": ["Full Plate Armor"],

    "shield": ["Round Shield", "Kite Shield", "Tower Shield"]
}

round_shield = OffHand(
    name="Round Shield",
    char="rsh",
    color=(175, 175, 175),
    description="A round shield.",
    defense_bonus=1, # Adds 1 to base AC
    price=15,
    category="shield"

)

kite_shield = OffHand(
    name="Kite Shield",
    char="ksh",
    color=(175, 175, 175),
    description="A kite shield.",
    defense_bonus=2, 
    price=35,
    category="shield"
)

tower_shield = OffHand(
    name="Tower Shield",
    char="tsh",
    color=(175, 175, 175),
    description="A tower shield.",
    defense_bonus=3, 
    price=50,
    category="shield"
)

padded_armor = Armor(
    name="Padded Armor",
    char="pda",
    color=(139, 69, 19),
    description="Light leather armor.",
    ac_bonus=1, # Adds 1 to base AC
    price = 10,
    category="light"
)

studded_leather_armor = Armor(
    name="Studded Leather Armor",
    char="sla",
    color=(139, 69, 19),
    description="A studded leather armor.",
    ac_bonus=2,
    price=20,
    category="light"
)

chainmail_armor = Armor(
    name="Chainmail Armor",
    char="cha",
    color=(175, 175, 175),
    description="Chainmail armor.",
    ac_bonus=3, # Adds 1 to base AC
    price = 10,
    category="medium"
)

half_plate_armor = Armor(
    name="Half Plate Armor",
    char="hpa",
    color=(175, 175, 175),
    description="A half plate armor.",
    ac_bonus=4,
    price=30,
    category="medium"
)

full_plate_armor = Armor(
    name="Full Plate Armor",
    char="fpa",
    color=(175, 175, 175),
    description=("Full plate armor."),
    ac_bonus=6,
    price=50,
    category="heavy"
)

robes = Armor(
    name="Robes",
    char="rbs", # Using same char as other armor for now
    color=(100, 100, 200),
    description="Simple cloth robes.",
    ac_bonus=0, # Robes typically provide no AC bonus, relying on Dex
    price = 10,
    category="light"
)

robes_of_protection = Armor(
    name="Robes of Protection",
    char="rop",
    color=(150, 20, 20),
    description="A robe infused with protection magic.",
    ac_bonus=4,
    price=40,
    category="light"
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
    loot_pool = [
        lesser_healing_potion, greater_healing_potion, padded_armor, studded_leather_armor, chainmail_armor, half_plate_armor,
        robes, iron_dagger, silver_dagger, iron_short_sword, bronze_short_sword, iron_long_sword, steel_long_sword, oak_staff, 
        apprentices_staff, pole_arm, steel_battle_axe, steel_rapier, iron_hammer, steel_maul, steel_mace, dwarven_flail,
        round_shield, kite_shield, tower_shield, torch
    ]

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
