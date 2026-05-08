import random
from world.tile import floor, MimicTile, TrapTile

from core.status_effects import DivineStrikeBuff, PowerAttackBuff, EvasionBuff, PreciseStrikeBuff, Prepared, FleetFooted, AppliedToxins
from core.game import GameState
from entities.monster import Monster, Mimic
from entities.summons import MageHandEntity, Imp, Celestial, SpiritualWeaponEntity
from entities.base_entity import NPC
from core.floating_text import FloatingText
from items.items import Potion, Food, OffHand, lesser_healing_potion, greater_healing_potion, meat, green_apple, fromage, bread, mushroom, torch, wood_plank, throwing_knife # NEW: Import for potion drop


class Ability:
    def __init__(self, name, description, cost=0, cooldown=0):
        self.name = name
        self.description = description
        self.cost = cost # e.g., mana, stamina, uses per rest
        self.cooldown = cooldown # turns until usable again
        self.current_cooldown = 0

    def can_use(self, user, game_instance):
        """Checks if the user can currently use this ability."""
        if self.current_cooldown > 0:
            game_instance.message_log.add_message(f"{self.name} is on cooldown ({self.current_cooldown} turns left).", (255, 150, 0))
            return False
        # Add checks for cost (e.g., if user has enough mana/stamina) later
        return True

    def use(self, user, game_instance):
        """Abstract method to be implemented by specific abilities."""
        if not self.can_use(user, game_instance): # <--- THIS IS THE CRITICAL CHECK
            return False # <--- If cannot use, immediately return False and do nothing else
        
        # Apply cost and set cooldown (common to all abilities)
        # user.spend_resource(self.cost) # Implement this in Player class later
        self.current_cooldown = self.cooldown
        
        game_instance.message_log.add_message(f"{user.name} uses {self.name}!", (100, 255, 255))
        return True # Indicate successful use

    def tick_cooldown(self):
        """Decrements the cooldown each turn."""
        if self.current_cooldown > 0:
            self.current_cooldown -= 1


    def execute_on_target(self, user, game_instance, target_x, target_y):
        """
        Performs the Mage Hand effect on the selected target.
        """
        target_tile = game_instance.game_map.tiles[target_y][target_x]

        # Check if the target is a TrapTile
        if isinstance(target_tile, TrapTile) and not target_tile.trap_instance.is_triggered:
            game_instance.message_log.add_message(f"The Mage Hand triggers the {target_tile.trap_instance.name}!", (255, 255, 0))

            # Pass the actual player object instead of "Mage Hand"
            target_tile.trap_instance.trigger(user, game_instance, target_x, target_y)  # Pass the player object
            return True  # Action successful, end turn

        game_instance.message_log.add_message("Mage Hand cannot interact with that target.", (255, 150, 0))
        return False  # Invalid target, stay in targeting mode

# --- Innate Abilities ---

class SpotTrapsAbility(Ability):
    def __init__(self):
        # Cooldown: e.g., 10 turns. Cost: 0 for now, could be stamina later.
        super().__init__("Spot Traps", "Actively search for hidden traps in a 5-tile radius.", cost=0, cooldown=3)

    def use(self, user, game_instance):
        if not super().use(user, game_instance): # Handles cooldown check
            return False
        
        game_instance.message_log.add_message(f"{user.name} actively searches for traps...", (100, 255, 255))
        
        # Check for traps in a 5 tile radius
        adjacent_traps = []
        radius = 4
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if dx == 0 and dy == 0:
                    continue  # Skip self
                check_x = user.x + dx
                check_y = user.y + dy
                if 0 <= check_x < game_instance.game_map.width and 0 <= check_y < game_instance.game_map.height:
                    tile = game_instance.game_map.tiles[check_y][check_x]
                    if isinstance(tile, TrapTile) and tile.trap_instance.is_hidden:
                        adjacent_traps.append(tile)
        
        if adjacent_traps:
            # Perform an Intelligence (Investigation) check
            investigation_bonus = user.get_ability_modifier(user.intelligence)
            if "investigation" in user.skill_proficiencies:
                investigation_bonus += user.proficiency_bonus
            d20_roll = random.randint(1, 20)
            investigation_check_total = d20_roll + investigation_bonus
            
            found_any = False
            for trap_tile in adjacent_traps:
                if investigation_check_total >= trap_tile.trap_instance.detection_dc:
                    trap_tile.trap_instance.reveal(game_instance, trap_tile.x, trap_tile.y)
                    game_instance.message_log.add_message(f"You successfully find a hidden {trap_tile.trap_instance.name}!", (0, 255, 255))
                    found_any = True
                # Else: The message for failing to find *any* traps is handled below.
            
            if not found_any:
                game_instance.message_log.add_message(f"You fail to find any traps nearby.", (150, 150, 150))
        else:
            game_instance.message_log.add_message("You don't see any traps nearby.", (150, 150, 150))
        
        return True # Indicate successful use and end turn


class DisarmTrapsAbility(Ability):
    def __init__(self):
        # Cooldown: e.g., 15 turns. Cost: 0 for now.
        super().__init__("Disarm Traps", "Attempt to disarm a revealed trap in an adjacent tile.", cost=0, cooldown=3)

    def use(self, user, game_instance):
        if not super().use(user, game_instance): # Handles cooldown check
            return False
        
        game_instance.message_log.add_message(f"{user.name} prepares to disarm a trap...", (100, 255, 255))
        
        # Check all adjacent tiles for revealed traps
        disarmable_traps = []
        for dx in [0, -1, 1]:  # Check adjacent tiles
            for dy in [0, -1, 1]:
                if abs(dx) + abs(dy) == 1:  # Only cardinal directions for disarming
                    check_x = user.x + dx
                    check_y = user.y + dy
                    if 0 <= check_x < game_instance.game_map.width and 0 <= check_y < game_instance.game_map.height:
                        tile = game_instance.game_map.tiles[check_y][check_x]
                        if isinstance(tile, TrapTile) and not tile.trap_instance.is_hidden and not tile.trap_instance.is_disarmed:
                            disarmable_traps.append(tile)
        
        if disarmable_traps:
            # For simplicity, we'll auto-target the first disarmable trap found.
            # You could implement a targeting mode similar to FireBolt if you want the player to choose.
            target_tile = disarmable_traps[0]

            # Check if the player has Thieves' Tools in their inventory
            has_tools = any(item.name == "Thieves' Tools" for item in user.inventory.items)
            
            if has_tools:
                if target_tile.trap_instance.attempt_disarm(user, game_instance, target_tile.x, target_tile.y):
                    game_instance.message_log.add_message(f"Disarmed the {target_tile.trap_instance.name}!", (0, 255, 0))
                else:
                    game_instance.message_log.add_message(f"Failed to disarm the {target_tile.trap_instance.name}!", (255, 100, 100))
            else:
                game_instance.message_log.add_message("You need Thieves' Tools to disarm traps.", (255, 0, 0))
        else:
            game_instance.message_log.add_message("No disarmable traps adjacent to you.", (150, 150, 150))
        
        return True # Indicate successful use and end turn




# --- Specific Abilities ---

class SecondWind(Ability):
    def __init__(self):
        super().__init__("Second Wind", "Heal yourself for a small amount of HP.", cooldown=75) # 75 turns cooldown

    def use(self, user, game_instance):
        # Call base class use to handle cooldown and initial checks.
        # If base.use returns False (because can_use failed), then this method should also return False.
        if not super().use(user, game_instance):
            return False
        
        heal_amount = user.level * 2 + 8 # Example: Heals based on level
        amount_healed = user.heal(heal_amount)
        game_instance.message_log.add_message(f"{user.name} regains {amount_healed} HP!", (0, 255, 0))
        return True # Indicate successful use


class PowerAttack(Ability):
    def __init__(self):
        super().__init__("Power Attack", "Sacrifice accuracy for increased damage on your next attack.", cooldown=15)
        # PowerAttack doesn't need a 'range' attribute here because it's not a direct targeted ability.
        # It modifies the *next* melee attack.
    def use(self, user, game_instance):
        if not super().use(user, game_instance):
            return False
        
        # Apply the PowerAttackBuff to the user
        user.add_status_effect("PowerAttackBuff", duration=2, game_instance=game_instance) # Duration 1 means it lasts for the next turn/attack
        
        game_instance.message_log.add_message(f"{user.name} prepares a Power Attack!", (255, 165, 0))
        
        # Power Attack does NOT enter targeting mode. It just applies a buff.
        # The player's turn should end after using this ability.
        return True # Indicate successful use and end turn
    
    def scale_with_level(self, player_level):
        """
        Scales the Power Attack ability with player level.
        Increases extra damage dice by 1 for every 4 levels.
        """
        additional_dice = (player_level - 1) // 4
        PowerAttackBuff.base_extra_damage_dice = 1 + additional_dice

        print(f"[DEBUG] {self.name} scaled: extra_damage_dice = {PowerAttackBuff.base_extra_damage_dice} at player level {player_level}")

class Parry(Ability):
    def __init__(self):
        super().__init__("Parry", "Focus on defense, increasing your chance to block incoming attacks for 3 turns.", cooldown=15)
        self.base_ac_bonus = 3
        self.ac_bonus = self.base_ac_bonus
        self.duration = 3

    def use(self, user, game_instance):
        if not super().use(user, game_instance):
            return False
        
        # Apply the ParryBuff to the user with the current AC bonus.
        user.add_status_effect("ParryBuff", self.duration, game_instance=game_instance, source=self)
        
        game_instance.message_log.add_message(f"{user.name} takes a defensive stance, gaining +{self.ac_bonus} AC!", (100, 255, 100))
        
        # Parry does NOT enter targeting mode. It just applies a buff.
        # The player's turn should end after using this ability.
        return True # Indicate successful use and end turn
    
    def scale_with_level(self, player_level):
        additional_ac = (player_level - 1) // 4  # +1 AC every 4 levels
        self.ac_bonus = self.base_ac_bonus + additional_ac
        print(f"[DEBUG] {self.name} scaled: ac_bonus = {self.ac_bonus} at player level {player_level}")

class PreciseStrike(Ability):
    def __init__(self):
        super().__init__("Precise Strike", "Focus your aim, increasing your attack bonus for 10 turns.", cooldown=20)

    def use(self, user, game_instance):
        if not super().use(user, game_instance):
            return False
        
        # Apply the PreciseStrikeBuff to the user
        user.add_status_effect("PreciseStrikeBuff", duration=10, game_instance=game_instance)
        
        game_instance.message_log.add_message(f"{user.name} focuses their aim!", (0, 255, 255))
        
        # This ability does NOT enter targeting mode. It just applies a buff.
        # The player's turn should end after using this ability.
        return True # Indicate successful use and end turn
    
    def scale_with_level(self, player_level):
        """
        Scales the Precise Strike ability with player level.
        Increases attack bonus modifier by 1 for every 4 levels.
        """
        additional_bonus = (player_level - 1) // 4
        PreciseStrikeBuff.base_attack_bonus_modifier = 5 + additional_bonus

        print(f"[DEBUG] {self.name} scaled: attack_bonus_modifier = {PreciseStrikeBuff.base_attack_bonus_modifier} at player level {player_level}")


class PrepTime(Ability):
    def __init__(self):
        super().__init__("Prep Time", "Prepare for battle: gain defense, extra attack power, and coat your weapons in toxins.", cooldown=20)

    def use(self, user, game_instance):
        if not super().use(user, game_instance):
            return False

        user.add_status_effect("Prepared", duration=10, game_instance=game_instance)
        user.add_status_effect("FleetFooted", duration=10, game_instance=game_instance)
        user.add_status_effect("AppliedToxins", duration=10, game_instance=game_instance)

        game_instance.message_log.add_message(f"{user.name} takes prep time, readying their strikes and their defenses.", (0, 255, 255))
        return True
    
    def scale_with_level(self, player_level):
        """
        Scales the Prep Time ability with player level.
        Increases attack power modifier and defense bonus every 4 levels.
        """
        additional_attack_bonus = (player_level - 1) // 4
        additional_defense_bonus = (player_level - 1) // 4

        Prepared.base_attack_power_modifier = 2 + additional_attack_bonus
        FleetFooted.base_ac_bonus = 2 + additional_defense_bonus
        AppliedToxins.base_poison_damage_dice = 1 + additional_attack_bonus

        print(f"[DEBUG] {self.name} scaled: attack_power_modifier = {Prepared.base_attack_power_modifier}, ac_bonus = {FleetFooted.base_ac_bonus}, poison_damage_dice = {AppliedToxins.base_poison_damage_dice} at player level {player_level}")


class Guard(Ability):
    def __init__(self):
        super().__init__("Guard", "Brace behind your shield, increasing your armor class for a short time.", cost=0, cooldown=10)
        self.base_ac_bonus = 5
        self.ac_bonus = self.base_ac_bonus
        self.duration = 4

    def use(self, user, game_instance):
        if not user.equipped_off_hand or getattr(user.equipped_off_hand, 'category', '').lower() != 'shield':
            game_instance.message_log.add_message("You must have a shield equipped to Guard!", (255, 100, 100))
            return False

        if not super().use(user, game_instance):
            return False

        # Apply the Guard status effect with the current AC bonus.
        user.add_status_effect("Guard", self.duration, game_instance, source=self)
        game_instance.message_log.add_message(f"{user.name} braces behind the shield, gaining +{self.ac_bonus} AC!", (100, 255, 100))
        return True

    def scale_with_level(self, player_level):
        additional_ac = (player_level - 1) // 4  # +1 AC every 4 levels
        self.ac_bonus = self.base_ac_bonus + additional_ac
        print(f"[DEBUG] {self.name} scaled: ac_bonus = {self.ac_bonus} at player level {player_level}")


class CunningActionDash(Ability):
    def __init__(self):
        super().__init__("Cunning Action: Dash", "Use a bonus action to Dash.", cooldown=5)

    def use(self, user, game_instance):
        if not super().use(user, game_instance):
            return False
        
        # Set the player's action state to indicate a choice is pending
        user.current_action_state = "cunning_action_dash"  # Changed to only allow Dash
        game_instance.message_log.add_message(f"{user.name} prepares a Cunning Action: Dash!", (100, 255, 255))
        return True  # Indicate successful use of the ability (bonus action consumed)
  

class Evasion(Ability):
    def __init__(self):
        super().__init__("Evasion", "Become incredibly agile, greatly increasing dodge chance and taking half damage if hit. Lasts 3 turns.", cooldown=29)

    def use(self, user, game_instance):
        if not super().use(user, game_instance):
            return False
        
        user.add_status_effect("EvasionBuff", duration=10, game_instance=game_instance)
        return True


class ThrowKnife(Ability):
    def __init__(self):
        super().__init__("Throw Knife", "Hurl a throwing knife at a foe.", cost=0, cooldown=2)
        self.range = 6  # Range in tiles
        self.damage_dice = 1  # 1d4
        self.is_bonus_action = True  # This ability can be used as a bonus action

    def use(self, user, game_instance):
        # Check if user has a throwing knife in inventory or equipped
        has_throwing_knife = False
        
        # Check if equipped as off-hand
        if user.equipped_off_hand and user.equipped_off_hand.name.lower() == "throwing knife":
            has_throwing_knife = True
        
        # Check if in inventory
        if not has_throwing_knife:
            for item in user.inventory.items:
                if item.name.lower() == "throwing knife":
                    has_throwing_knife = True
                    break
        
        if not has_throwing_knife:
            game_instance.message_log.add_message(f"You don't have a throwing knife!", (255, 100, 100))
            return False

        if not super().use(user, game_instance):
            return False

        # Helper: footprint-aware visibility
        def is_entity_visible(ent):
            allowed = ['player', 'torch', 'darkvision']
            size = getattr(ent, 'footprint_size', 1)
            if size > 1:
                for oy in range(size):
                    for ox in range(size):
                        if game_instance.fov.get_visibility_type(ent.x + ox, ent.y + oy) in allowed:
                            return True
                return False
            return game_instance.fov.get_visibility_type(ent.x, ent.y) in allowed

        # Helper: footprint-aware distance (min distance to any occupied tile)
        def distance_to_entity(ent):
            size = getattr(ent, 'footprint_size', 1)
            if size > 1:
                best = None
                for oy in range(size):
                    for ox in range(size):
                        d = user.distance_to(ent.x + ox, ent.y + oy)
                        if best is None or d < best:
                            best = d
                return best if best is not None else 9999
            return user.distance_to(ent.x, ent.y)

        # Find only monster targets within range (footprint-aware)
        monster_targets = []
        for entity in game_instance.entities:
            if isinstance(entity, Monster) and entity.alive:
                distance = distance_to_entity(entity)
                if distance <= self.range:  # Check against ability range
                    if is_entity_visible(entity):  # Footprint-aware FOV
                        monster_targets.append(entity)
        
        # If there are monster targets, auto-target the closest one
        if monster_targets:
            target = min(monster_targets, key=lambda m: user.distance_to(m.x, m.y))
            
            # Set the game state to targeting mode
            game_instance.game_state = GameState.TARGETING
            game_instance.ability_in_use = self  # Store which ability is being used
            game_instance.targeting_ability_range = self.range
            
            # Initialize targeting cursor at the auto-selected monster's position
            game_instance.targeting_cursor_x = target.x
            game_instance.targeting_cursor_y = target.y
            
            game_instance.message_log.add_message(f"{user.name} prepares to throw a knife! Auto-targeting {target.name}.", (100, 255, 100))
            return True  # Indicate successful initiation of targeting
        else:
            game_instance.message_log.add_message(f"{user.name} prepares to throw a knife! No enemies in range.).", (100, 255, 100))
            game_instance.game_state = GameState.TARGETING
            game_instance.ability_in_use = self  # Store which ability is being used
            game_instance.targeting_ability_range = self.range
            
            # Initialize targeting cursor at player's position
            game_instance.targeting_cursor_x = user.x
            game_instance.targeting_cursor_y = user.y
            
            return True  # Indicate successful initiation of targeting

    def execute_on_target(self, user, game_instance, target_x, target_y):
        """
        Performs the Throw Knife effect on the selected target.
        """
        target_monster = game_instance.get_target_at(target_x, target_y)

        # Check if the target is within the player's FOV
        if not game_instance.fov.get_visibility_type(target_x, target_y) in ['player', 'torch', 'darkvision']:
            game_instance.message_log.add_message(f"You cannot throw at {target_x}, {target_y} because it is out of sight!", (255, 0, 0))
            return False  # Do not consume a turn

        if not game_instance.check_line_of_sight(user.x, user.y, target_x, target_y):
            game_instance.message_log.add_message(f"A wall blocks your throw to {target_x}, {target_y}!", (255, 0, 0))
            return False  # Do not consume a turn

        # Check if the target is a valid monster
        if not target_monster or not isinstance(target_monster, Monster):
            game_instance.message_log.add_message("Throw Knife requires a monster target.", (255, 150, 0))
            return False  # Invalid target, do not consume a turn

        # Remove throwing knife from inventory or unequip it
        knife_to_throw = None
        attack_modifier = user.get_ability_modifier(user.dexterity) + user.proficiency_bonus

        # Check if equipped as off-hand
        if user.equipped_off_hand and user.equipped_off_hand.name.lower() == "throwing knife":
            knife_to_throw = user.equipped_off_hand
            attack_modifier += getattr(knife_to_throw, "attack_bonus", 0)
            user.equipped_off_hand = None
            user.update_throw_knife_ability()
            game_instance.message_log.add_message(f"You throw your equipped {knife_to_throw.name}!", (100, 255, 100))
        else:
            # Search inventory for throwing knife
            for item in user.inventory.items:
                if item.name.lower() == "throwing knife":
                    knife_to_throw = item
                    attack_modifier += getattr(item, "attack_bonus", 0)
                    user.inventory.remove_item(item)
                    user.update_throw_knife_ability()
                    game_instance.message_log.add_message(f"You throw a {knife_to_throw.name} from your inventory!", (100, 255, 100))
                    break

        if not knife_to_throw:
            game_instance.message_log.add_message(f"No throwing knife found!", (255, 0, 0))
            return False

        # Roll to hit with a d20
        d20_roll = random.randint(1, 20)
        attack_roll_total = d20_roll + attack_modifier
        target_ac = getattr(target_monster, "armor_class", 10)

        game_instance.message_log.add_message(
            f"You roll a d20: [{d20_roll}] + [{attack_modifier}] = {attack_roll_total} vs AC {target_ac}",
            (200, 200, 255)
        )

        is_critical_hit = (d20_roll == 20)
        is_critical_fumble = (d20_roll == 1)

        if is_critical_hit:
            game_instance.message_log.add_message("CRITICAL HIT! The knife finds a weak point!", (255, 255, 0))
            hit_successful = True
        elif is_critical_fumble:
            game_instance.message_log.add_message("CRITICAL FUMBLE! Your throw goes wild.", (255, 0, 0))
            hit_successful = False
        else:
            hit_successful = attack_roll_total >= target_ac

        if hit_successful:
            hit_messages = [
                f"A throwing knife streaks towards the {target_monster.name}!",
                f"Your knife spins through the air and strikes the {target_monster.name}!",
                f"The {target_monster.name} is hit by your throwing knife!",
            ]
            game_instance.message_log.add_message(random.choice(hit_messages), (255, 100, 100))

            damage_modifier = user.get_ability_modifier(user.dexterity)
            damage_rolls = [random.randint(1, 4) for _ in range(self.damage_dice)]
            total_damage = sum(damage_rolls) + damage_modifier

            game_instance.message_log.add_message(f"You roll {self.damage_dice}d4 for damage: {damage_rolls} + [{damage_modifier}] (DEX Modifier) = {total_damage} damage!", (255, 100, 0))

            if isinstance(target_monster, Mimic):
                damage_dealt = target_monster.take_damage(total_damage, game_instance)
            else:
                damage_dealt = target_monster.take_damage(total_damage, game_instance)

            game_instance.message_log.add_message(f"A knife strikes {target_monster.name} for {damage_dealt} damage!", (255, 100, 100))
            game_instance.message_log.add_message(f"{target_monster.name} has {target_monster.hp}/{target_monster.max_hp} HP", (100, 255, 100))

            hit_text = FloatingText(target_monster.x, target_monster.y, "HIT!", (255, 255, 0))
            game_instance.floating_texts.append(hit_text)

            damage_text = FloatingText(target_monster.x, target_monster.y - 0.5, str(damage_dealt), (255, 0, 0))
            game_instance.floating_texts.append(damage_text)

            if not target_monster.alive:
                xp_gained = target_monster.die(game_instance, killer=user)
                user.gain_xp(xp_gained, game_instance)
        else:
            miss_messages = [
                f"Your knife sails past the {target_monster.name}!",
                f"The {target_monster.name} narrowly avoids your thrown knife!",
                f"You miss the {target_monster.name} with your throw!",
            ]
            game_instance.message_log.add_message(random.choice(miss_messages), (255, 150, 150))

            miss_text = FloatingText(target_x, target_y, "MISS!", (255, 150, 150))
            game_instance.floating_texts.append(miss_text)

        # Place the thrown knife at the target location regardless of hit or miss
        knife_to_throw.x = target_x
        knife_to_throw.y = target_y
        game_instance.game_map.items_on_ground.append(knife_to_throw)
        game_instance.message_log.add_message(f"The {knife_to_throw.name} lands at ({target_x}, {target_y}).", (150, 150, 150))

        return True  # Successfully used ability

    def scale_with_level(self, player_level):
        """
        Scales the Throw Knife ability with player level.
        Increases damage dice by 1 for every 4 levels.
        """
        additional_dice = (player_level - 1) // 4  # One extra die every 4 levels
        self.damage_dice = 1 + additional_dice


class FireBolt(Ability):
    def __init__(self):
        super().__init__("Fire Bolt", "Hurl a searing bolt of fire at a foe.", cost=0, cooldown=2)
        self.range = 6  # Example range in tiles
        self.damage_dice = 1 # Initial damage dice (e.g., 1d10)

    def use(self, user, game_instance):
        if not super().use(user, game_instance):
            return False

        # Helper: footprint-aware visibility
        def is_entity_visible(ent):
            allowed = ['player', 'torch', 'darkvision']
            size = getattr(ent, 'footprint_size', 1)
            if size > 1:
                for oy in range(size):
                    for ox in range(size):
                        if game_instance.fov.get_visibility_type(ent.x + ox, ent.y + oy) in allowed:
                            return True
                return False
            return game_instance.fov.get_visibility_type(ent.x, ent.y) in allowed

        # Helper: footprint-aware distance (min distance to any occupied tile)
        def distance_to_entity(ent):
            size = getattr(ent, 'footprint_size', 1)
            if size > 1:
                best = None
                for oy in range(size):
                    for ox in range(size):
                        d = user.distance_to(ent.x + ox, ent.y + oy)
                        if best is None or d < best:
                            best = d
                return best if best is not None else 9999
            return user.distance_to(ent.x, ent.y)

        # Find only monster targets within range (footprint-aware)
        monster_targets = []
        for entity in game_instance.entities:
            if isinstance(entity, Monster) and entity.alive:
                distance = distance_to_entity(entity)
                if distance <= self.range:  # Check against ability range
                    if is_entity_visible(entity):  # Footprint-aware FOV
                        monster_targets.append(entity)
        # If there are monster targets, auto-target the closest one
        if monster_targets:
            target = min(monster_targets, key=lambda m: user.distance_to(m.x, m.y))
            
            # Set the game state to targeting mode
            game_instance.game_state = GameState.TARGETING
            game_instance.ability_in_use = self  # Store which ability is being used
            game_instance.targeting_ability_range = self.range
            
            # Initialize targeting cursor at the auto-selected monster's position
            game_instance.targeting_cursor_x = target.x
            game_instance.targeting_cursor_y = target.y
            
            game_instance.message_log.add_message(f"{user.name} prepares Fire Bolt! Auto-targeting {target.name}.", (255, 100, 0))
            return True  # Indicate successful initiation of targeting
        
        # If no monster targets are found, revert to manual targeting starting at player
        else:
            game_instance.message_log.add_message(f"{user.name} prepares Fire Bolt! No enemies in range).", (255, 100, 0))
            game_instance.game_state = GameState.TARGETING
            game_instance.ability_in_use = self  # Store which ability is being used
            game_instance.targeting_ability_range = self.range
            
            # Initialize targeting cursor at player's position
            game_instance.targeting_cursor_x = user.x
            game_instance.targeting_cursor_y = user.y
            
            return True  # Indicate successful initiation of targeting

    def execute_on_target(self, user, game_instance, target_x, target_y):
        """
        Performs the Fire Bolt effect on the selected target.
        """
        target_monster = game_instance.get_target_at(target_x, target_y)
        target_tile = game_instance.game_map.tiles[target_y][target_x]  # Get the tile object at target

        # Check if the target is within the player's FOV (tile or any tile of monster footprint)
        if not game_instance.fov.get_visibility_type(target_x, target_y) in ['player', 'torch', 'darkvision']:
            game_instance.message_log.add_message(f"You cannot attack {target_x}, {target_y} because it is out of sight!", (255, 0, 0))
            return False  # Do not consume a turn

        if not game_instance.check_line_of_sight(user.x, user.y, target_x, target_y):
            game_instance.message_log.add_message(f"A wall blocks your shot to {target_x}, {target_y}!", (255, 0, 0))
            return False # Do not consume a turn

        target_monster = game_instance.get_target_at(target_x, target_y)
        target_tile = game_instance.game_map.tiles[target_y][target_x]  # Get the tile object at target        


        # Check if the target is a valid monster or destructible object
        if not (target_monster or target_tile.destructible):
            game_instance.message_log.add_message("Fire Bolt requires a monster target or a destructible object.", (255, 150, 0))
            return False  # Invalid target, do not consume a turn

        # Fire Bolt damage calculation (example: 1d10)
        # Use self.damage_dice for the number of d10s
        damage_rolls = [random.randint(1, 10) for _ in range(self.damage_dice)]
        total_damage = sum(damage_rolls)

        game_instance.message_log.add_message(f"You roll {self.damage_dice}d10 for damage: {damage_rolls} = {total_damage}", (255, 100, 0))

        if target_monster and isinstance(target_monster, Monster):
            # Check if the target is specifically a Mimic
            hit_messages = [
                f"A searing bolt of fire streaks towards the {target_monster.name}!",
                f"Flames erupt as your spell connects with the {target_monster.name}!",
                f"The {target_monster.name} is engulfed in magical fire!",
            ]
            game_instance.message_log.add_message(random.choice(hit_messages), (255, 165, 0))

            if isinstance(target_monster, Mimic):
                damage_dealt = target_monster.take_damage(total_damage, game_instance) 
            else:
                damage_dealt = target_monster.take_damage(total_damage, game_instance)  # Pass game_instance here

            game_instance.message_log.add_message(f"A bolt of fire strikes {target_monster.name} for {damage_dealt} damage!", (255, 165, 0))
            game_instance.message_log.add_message(f"{target_monster.name} has {target_monster.hp}/{target_monster.max_hp} HP", (255, 165, 0))

            # Add FloatingText for "HIT!" and damage dealt
            hit_text = FloatingText(target_monster.x, target_monster.y, "HIT!", (255, 255, 0))
            game_instance.floating_texts.append(hit_text)

            damage_text = FloatingText(target_monster.x, target_monster.y - 0.5, str(damage_dealt), (255, 0, 0))  # <--- ADJUSTED Y
            game_instance.floating_texts.append(damage_text)

            if not target_monster.alive:
                xp_gained = target_monster.die(game_instance, killer=user)
                user.gain_xp(xp_gained, game_instance)  # Use 'user' (player) here
            return True  # Successfully used ability

        elif target_tile.destructible:  # <--- NEW: Check if the tile is destructible
            destructible_messages = [
                f"Your Fire Bolt incinerates the {target_tile.name}!",
                f"A magical inferno consumes the {target_tile.name}!",
            ]
            game_instance.message_log.add_message(random.choice(destructible_messages), (255, 165, 0))                

            # For simplicity, we'll assume Fire Bolt instantly destroys destructible tiles
            # In a more complex system, destructible tiles might have HP.
            game_instance.message_log.add_message(f"Your Fire Bolt smashes the {target_tile.name}!", (255, 165, 0))
            game_instance.game_map.tiles[target_y][target_x] = floor  # Replace with floor tile
            self.minimap_needs_redraw = True # Map changed, redraw minimap
            
            # --- 10% chance to drop a healing potion ---            
            if target_tile.name in ["Crate", "Barrel"]: # Check if it was a crate or barrel 
                if random.random() < 0.70:
                    new_junk = wood_plank.__class__(
                        name=wood_plank.name,
                        char=wood_plank.char,
                        color=wood_plank.color,
                        description=wood_plank.description
                    )
                    new_junk.x = target_x
                    new_junk.y = target_y
                    game_instance.game_map.items_on_ground.append(new_junk)
                elif random.random() < 0.3:
                    new_torch = torch.__class__(
                        name=torch.name,
                        char=torch.char,
                        color=torch.color,
                        description=torch.description,
                        price=torch.price
                    )
                    new_torch.x = target_x
                    new_torch.y = target_y
                    game_instance.game_map.items_on_ground.append(new_torch)
                    game_instance.message_log.add_message(f"A {new_torch.name} drops from the {target_tile.name}!", new_torch.color)
                elif random.random() < 0.2:
                    new_food = meat.__class__(
                        name=meat.name,
                        char=meat.char,
                        color=meat.color,
                        description=meat.description,
                        healing_value=meat.healing_value,
                        price=meat.price
                    )
                    new_food.x = target_x
                    new_food.y = target_y
                    game_instance.game_map.items_on_ground.append(new_food)
                    game_instance.message_log.add_message(f"A {new_food.name} drops from the {target_tile.name}!", new_food.color)
                elif random.random() < 0.35:
                    new_food = green_apple.__class__(
                        name=green_apple.name,
                        char=green_apple.char,
                        color=green_apple.color,
                        description=green_apple.description,
                        healing_value=green_apple.healing_value,
                        price=green_apple.price
                    )
                    new_food.x = target_x
                    new_food.y = target_y
                    game_instance.game_map.items_on_ground.append(new_food)
                    game_instance.message_log.add_message(f"A {new_food.name} drops from the {target_tile.name}!", new_food.color)
                elif random.random() < 0.25:
                    new_food = fromage.__class__(
                        name=fromage.name,
                        char=fromage.char,
                        color=fromage.color,
                        description=fromage.description,
                        healing_value=fromage.healing_value,
                        price=fromage.price
                    )
                    new_food.x = target_x
                    new_food.y = target_y
                    game_instance.game_map.items_on_ground.append(new_food)
                    game_instance.message_log.add_message(f"A {new_food.name} drops from the {target_tile.name}!", new_food.color) 
                elif random.random() < 0.3:
                    new_food = bread.__class__(
                        name=bread.name,
                        char=bread.char,
                        color=bread.color,
                        description=bread.description,
                        healing_value=bread.healing_value,
                        price=bread.price
                    )
                    new_food.x = target_x
                    new_food.y = target_y
                    game_instance.game_map.items_on_ground.append(new_food)
                    game_instance.message_log.add_message(f"A {new_food.name} drops from the {target_tile.name}!", new_food.color) 
                elif random.random() < 0.4:
                    new_food = mushroom.__class__(
                        name=mushroom.name,
                        char=mushroom.char,
                        color=mushroom.color,
                        description=mushroom.description,
                        healing_value=mushroom.healing_value,
                        price=mushroom.price
                    )
                    new_food.x = target_x
                    new_food.y = target_y
                    game_instance.game_map.items_on_ground.append(new_food)
                    game_instance.message_log.add_message(f"A {new_food.name} drops from the {target_tile.name}!", new_food.color)                 


            # --- MISSING FLOATING TEXT CREATION HERE FOR DESTRUCTIBLE ---
            game_instance.floating_texts.append(FloatingText(target_x, target_y, "SMASH!", (255, 100, 0)))
            print(f"DEBUG: FireBolt added SMASH! FloatingText for {target_tile.name} at ({target_x},{target_y}). List size: {len(game_instance.floating_texts)}")  # <--- ADD THIS DEBUG

            # If it was a MimicTile, ensure the Mimic entity is also handled
            if isinstance(target_tile, MimicTile):
                mimic_entity = target_tile.mimic_entity
                if mimic_entity.disguised:
                    mimic_entity.reveal(game_instance)  # Reveal the mimic
                else:
                    game_instance.message_log.add_message(f"The {mimic_entity.name} is already revealed and takes no further damage from smashing its disguise.", (150, 150, 150))
            return True  # Successfully used ability
        else:
            game_instance.message_log.add_message("Fire Bolt requires a monster target or a destructible object.", (255, 150, 0))
            # --- MISSING FLOATING TEXT FOR MISS/INVALID TARGET ---
            game_instance.floating_texts.append(FloatingText(target_x, target_y, "INVALID!", (255, 0, 0)))
            print(f"DEBUG: FireBolt added INVALID! FloatingText for ({target_x},{target_y}). List size: {len(game_instance.floating_texts)}")  # <--- ADD THIS DEBUG
            return False  # Invalid target, stay in targeting mode

    def scale_with_level(self, player_level):
        """
        Scales the Fire Bolt ability with player level.
        Increases damage dice by 1 for every 4 levels (e.g., 1d10 at level 1, 2d10 at level 5, etc.)
        """
        additional_dice = (player_level - 1) // 5 # One extra die every 4 levels
        self.damage_dice = 1 + additional_dice
        print(f"[DEBUG] {self.name} scaled: damage_dice = {self.damage_dice} at player level {player_level}") 


class Fireball(Ability):
    def __init__(self):
        super().__init__("Fireball", "A bright streak flashes and explodes in a fiery blast.", cost=0, cooldown=100)
        self.radius = 4  # Radius of the fireball effect
        self.range = 8
        self.damage_dice = 8  # Number of damage dice (e.g., 8d6)

    def use(self, user, game_instance):
        if not super().use(user, game_instance):
            return False
        
        # Find only monster targets within range
        monster_targets = []
        for entity in game_instance.entities:
            if isinstance(entity, Monster) and entity.alive:
                distance = user.distance_to(entity.x, entity.y)
                if distance <= self.range:  # Check against ability range
                    # Check if the target is within the player's FOV
                    if game_instance.fov.get_visibility_type(entity.x, entity.y) in ['player', 'torch', 'darkvision']:
                        monster_targets.append(entity)
        # If there are monster targets, auto-target the closest one
        if monster_targets:
            target = min(monster_targets, key=lambda m: user.distance_to(m.x, m.y))
            
            # Set the game state to targeting mode
            game_instance.game_state = GameState.TARGETING
            game_instance.ability_in_use = self  # Store which ability is being used
            game_instance.targeting_ability_range = self.range
            
            # Initialize targeting cursor at the auto-selected monster's position
            game_instance.targeting_cursor_x = target.x
            game_instance.targeting_cursor_y = target.y
            
            game_instance.message_log.add_message(f"{user.name} conjures Fireball! Auto-targeting {target.name}.", (255, 100, 0))
            return True  # Indicate successful initiation of targeting
        
        # If no monster targets are found, revert to manual targeting starting at player
        else:
            game_instance.message_log.add_message(f"{user.name} conjures Fireball! No enemies in range. Select a target).", (255, 100, 0))
            game_instance.game_state = GameState.TARGETING
            game_instance.ability_in_use = self  # Store which ability is being used
            game_instance.targeting_ability_range = self.range
            
            # Initialize targeting cursor at player's position
            game_instance.targeting_cursor_x = user.x
            game_instance.targeting_cursor_y = user.y
            
            return True  # Indicate successful initiation of targeting

    def execute_on_target(self, user, game_instance, target_x, target_y):
        """
        Executes the Fireball effect on the selected target.
        """
        from entities.player import Player
        # Check if the target is within the player's FOV
        if not game_instance.fov.get_visibility_type(target_x, target_y) in ['player', 'torch', 'darkvision']:
            game_instance.message_log.add_message(f"You cannot cast Fireball at {target_x}, {target_y} because it is out of sight!", (255, 0, 0))
            return False  # Do not consume a turn

        # Calculate the damage
        # Use self.damage_dice for the number of d6s
        damage_rolls = [random.randint(1, 6) for _ in range(self.damage_dice)]  # Roll Xd6
        total_damage = sum(damage_rolls)

        # Notify the player of the damage
        game_instance.message_log.add_message(f"{user.name} casts Fireball and rolls {self.damage_dice}d6 {damage_rolls}.", (255, 165, 0))
        game_instance.message_log.add_message(f"Fireball deals {total_damage} fire damage!", (255, 165, 0))

        # Apply damage to all entities in the area of effect
        for entity in game_instance.entities:
            if entity.alive and self.is_within_radius(entity.x, entity.y, target_x, target_y, self.radius):
                if isinstance(entity, (Monster, Player)):
                    # Each entity makes a Dexterity saving throw
                    dexterity_save = entity.get_saving_throw_bonus("DEX")
                    d20_roll = random.randint(1, 20)
                    save_total = d20_roll + dexterity_save

                    game_instance.message_log.add_message(f"{entity.name} rolls a d20: {d20_roll} + {dexterity_save} = {save_total} (DC 15)", (200, 200, 255))

                    if save_total >= 15:  # Assuming a DC of 15 for Fireball
                        damage_dealt = total_damage // 2  # Half damage on success
                        game_instance.message_log.add_message(f"{entity.name} succeeds on the saving throw and takes {damage_dealt} fire damage!", (100, 255, 100))
                    else:
                        damage_dealt = total_damage  # Full damage on failure
                        game_instance.message_log.add_message(f"{entity.name} fails the saving throw and takes {damage_dealt} fire damage!", (255, 100, 100))

                    damage_dealt = entity.take_damage(damage_dealt, game_instance, damage_type='fire')  # Apply damage

                    # Create floating text for damage dealt
                    damage_text = FloatingText(entity.x, entity.y - 0.5, str(damage_dealt), (255, 0, 0))  # Adjust Y for visibility
                    game_instance.floating_texts.append(damage_text)  # Add to floating texts

                    # Check if the entity is dead and award XP
                    if not entity.alive:
                        if isinstance(entity, Monster):
                            xp_gained = entity.die(game_instance, killer=user)  # Pass game_instance to the die method
                            user.gain_xp(xp_gained, game_instance)  # Award XP to the player
                            game_instance.message_log.add_message(f"You gain {xp_gained} XP!", (100, 255, 100))  # Log the XP gained

        # Destroy destructible tiles in the area of effect
        for x in range(target_x - self.radius, target_x + self.radius + 1):
            for y in range(target_y - self.radius, target_y + self.radius + 1):
                if self.is_within_radius(x, y, target_x, target_y, self.radius):
                    # Ensure coordinates are within map bounds
                    if not (0 <= x < game_instance.game_map.width and 0 <= y < game_instance.game_map.height):
                        continue

                    target_tile = game_instance.game_map.tiles[y][x]

                    # --- NEW MIMIC REVEAL LOGIC ---
                    if isinstance(target_tile, MimicTile):
                        mimic_entity = target_tile.mimic_entity
                        if mimic_entity.disguised:
                            game_instance.message_log.add_message(f"The Fireball strikes the disguised {mimic_entity.name}!", (255, 165, 0))
                            # Mimics take damage from the fireball, which will trigger their reveal
                            # We pass the full damage of the fireball to the mimic
                            mimic_entity.take_damage(total_damage, game_instance, damage_type='fire')
                            # If the mimic is still disguised after taking damage (meaning it didn't die from the hit)
                            if mimic_entity.disguised: # Check again if it's still disguised
                                mimic_entity.reveal(game_instance) # Force reveal if it didn't die
                            # No need to replace the tile with floor here, as the mimic's reveal handles it.
                            game_instance.floating_texts.append(FloatingText(x, y, "REVEAL!", (255, 255, 0)))
                            game_instance.minimap_needs_redraw = True
                            continue # Move to the next tile in the radius

                    # --- EXISTING DESTRUCTIBLE TILE LOGIC (only if not a MimicTile) ---
                    if target_tile.destructible:
                        game_instance.message_log.add_message(f"The {target_tile.name} is destroyed by the Fireball!", (255, 0, 0))
                        game_instance.game_map.tiles[y][x] = floor  # Replace with floor tile
                        game_instance.minimap_needs_redraw = True  # Mark minimap for redraw

                        # Create floating text for the destruction of the tile
                        destruction_text = FloatingText(x, y - 0.5, f"SMASH!", (255, 0, 0))  # Adjust Y for visibility
                        game_instance.floating_texts.append(destruction_text)  # Add to floating texts

                        # --- Existing potion drop logic for crates/barrels ---
                        if target_tile.name in ["Crate", "Barrel"]: # Check if it was a crate or barrel 
                            if random.random() < 0.70:
                                new_junk = wood_plank.__class__(
                                    name=wood_plank.name,
                                    char=wood_plank.char,
                                    color=wood_plank.color,
                                    description=wood_plank.description
                                )
                                new_junk.x = x
                                new_junk.y = y
                                game_instance.game_map.items_on_ground.append(new_junk)
                            elif random.random() < 0.3:
                                new_torch = torch.__class__(
                                    name=torch.name,
                                    char=torch.char,
                                    color=torch.color,
                                    description=torch.description,
                                    price=torch.price
                                )
                                new_torch.x = x
                                new_torch.y = y
                                game_instance.game_map.items_on_ground.append(new_torch)
                                game_instance.message_log.add_message(f"A {new_torch.name} drops from the {target_tile.name}!", new_torch.color)
                            elif random.random() < 0.2:
                                new_food = meat.__class__(
                                    name=meat.name,
                                    char=meat.char,
                                    color=meat.color,
                                    description=meat.description,
                                    healing_value=meat.healing_value,
                                    price=meat.price
                                )
                                new_food.x = x
                                new_food.y = y
                                game_instance.game_map.items_on_ground.append(new_food)
                                game_instance.message_log.add_message(f"A {new_food.name} drops from the {target_tile.name}!", new_food.color)
                            elif random.random() < 0.35:
                                new_food = green_apple.__class__(
                                    name=green_apple.name,
                                    char=green_apple.char,
                                    color=green_apple.color,
                                    description=green_apple.description,
                                    healing_value=green_apple.healing_value,
                                    price=green_apple.price
                                )
                                new_food.x = x
                                new_food.y = y
                                game_instance.game_map.items_on_ground.append(new_food)
                                game_instance.message_log.add_message(f"A {new_food.name} drops from the {target_tile.name}!", new_food.color)
                            elif random.random() < 0.25:
                                new_food = fromage.__class__(
                                    name=fromage.name,
                                    char=fromage.char,
                                    color=fromage.color,
                                    description=fromage.description,
                                    healing_value=fromage.healing_value,
                                    price=fromage.price
                                )
                                new_food.x = x
                                new_food.y = y
                                game_instance.game_map.items_on_ground.append(new_food)
                                game_instance.message_log.add_message(f"A {new_food.name} drops from the {target_tile.name}!", new_food.color) 
                            elif random.random() < 0.3:
                                new_food = bread.__class__(
                                    name=bread.name,
                                    char=bread.char,
                                    color=bread.color,
                                    description=bread.description,
                                    healing_value=bread.healing_value,
                                    price=bread.price
                                )
                                new_food.x = x
                                new_food.y = y
                                game_instance.game_map.items_on_ground.append(new_food)
                                game_instance.message_log.add_message(f"A {new_food.name} drops from the {target_tile.name}!", new_food.color) 
                            elif random.random() < 0.4:
                                new_food = mushroom.__class__(
                                    name=mushroom.name,
                                    char=mushroom.char,
                                    color=mushroom.color,
                                    description=mushroom.description,
                                    healing_value=mushroom.healing_value,
                                    price=mushroom.price
                                )
                                new_food.x = x
                                new_food.y = y
                                game_instance.game_map.items_on_ground.append(new_food)
                                game_instance.message_log.add_message(f"A {new_food.name} drops from the {target_tile.name}!", new_food.color) 

        return True  # Successfully used ability

    def is_within_radius(self, x, y, center_x, center_y, radius):
        """Check if the (x, y) coordinates are within the radius of the center point."""
        return (x - center_x) ** 2 + (y - center_y) ** 2 <= radius ** 2
    
    def scale_with_level(self, player_level):
        """
        Scales the Fireball ability with player level.
        Increases damage dice by 1 for every 4 levels (e.g., 8d6 at level 1, 9d6 at level 5, etc.)
        """
        additional_dice = (player_level - 1) // 5 # One extra die every 4 levels
        self.damage_dice = 8 + additional_dice
        print(f"[DEBUG] {self.name} scaled: damage_dice = {self.damage_dice} at player level {player_level}") 


class MistyStep(Ability):
    def __init__(self):
        super().__init__("Misty Step", "The caster is briefly surrounded by silvery mist then vanishes, reappearing in an unoccupied space up to 6 tiles away.", cooldown=7)
        self.range = 6 # Max teleport distance in tiles

    def use(self, user, game_instance):
        if not super().use(user, game_instance):
            return False
        
        # Set the player's action state to indicate a choice is pending
        user.current_action_state = "misty_step_teleport" # A new state for Misty Step
        game_instance.message_log.add_message(f"{user.name} prepares to Misty Step! Select a destination).", (100, 255, 255))
        
        # Initialize targeting cursor at player's position for selection
        game_instance.targeting_cursor_x = user.x
        game_instance.targeting_cursor_y = user.y
        game_instance.targeting_ability_range = self.range # Set the range for the cursor
        game_instance.ability_in_use = self # Store the ability for targeting context
        game_instance.game_state = GameState.TARGETING # Enter targeting mode

        return True # Indicate successful initiation of the ability
    
    def execute_on_target(self, user, game_instance, target_x, target_y):
        """
        Performs the Misty Step teleport effect.
        """
        # Check if the target tile is walkable and not blocked by an entity
        if not game_instance.game_map.is_walkable(target_x, target_y):
            game_instance.message_log.add_message("Cannot Misty Step to an unwalkable space.", (255, 150, 0))
            return False # Invalid target, stay in targeting mode
        
        # Check if the target tile is occupied by another entity
        entity_at_target = game_instance.get_target_at(target_x, target_y) # Re-using get_target_at
        if entity_at_target:
            game_instance.message_log.add_message("Cannot Misty Step to an occupied space.", (255, 150, 0))
            return False # Invalid target, stay in targeting mode
        
        # Perform the teleport
        user.x = target_x
        user.y = target_y
        game_instance.message_log.add_message(f"{user.name} vanishes in a silvery mist and reappears!", (100, 255, 255))
        game_instance.update_fov() # Update FOV after teleporting
        return True # Successfully used ability    


class DetectMagic(Ability):
    def __init__(self):
        super().__init__("Detect Magic", "Detects hidden traps within a 4-tile radius.", cost=0, cooldown=3)

    def use(self, user, game_instance):
        if not super().use(user, game_instance):  # Handles cooldown check
            return False

        game_instance.message_log.add_message(f"{user.name} casts Detect Magic...", (100, 255, 255))

        # Check for hidden traps within 4-tile radius
        detected_traps = []
        for dx in range(-3, 5):
            for dy in range(-3, 5):
                if dx == 0 and dy == 0:
                    continue  # Skip self
                check_x = user.x + dx
                check_y = user.y + dy
                if 0 <= check_x < game_instance.game_map.width and 0 <= check_y < game_instance.game_map.height:
                    tile = game_instance.game_map.tiles[check_y][check_x]
                    if isinstance(tile, TrapTile) and tile.trap_instance.is_hidden:
                        detected_traps.append(tile)

        if detected_traps:
            for trap_tile in detected_traps:
                trap_tile.trap_instance.reveal(game_instance, trap_tile.x, trap_tile.y)
                game_instance.message_log.add_message(f"You detect a hidden {trap_tile.trap_instance.name}!", (0, 255, 255))
        else:
            game_instance.message_log.add_message("No traps detected nearby.", (150, 150, 150))

        return True  # Indicate successful use and end turn


class MageHand(Ability):
    def __init__(self):
        super().__init__("Mage Hand", "Summon a spectral hand to trigger traps or pick up items from a distance.", cost=0, cooldown=2)
        self.range = 6  # Max distance the Mage Hand can be controlled

    def use(self, user, game_instance):
        if not super().use(user, game_instance):
            return False

        game_instance.message_log.add_message("Select a target to trigger a trap or pick up an item).", (255, 100, 0))

        game_instance.game_state = GameState.TARGETING
        game_instance.ability_in_use = self
        game_instance.targeting_ability_range = self.range
        game_instance.targeting_cursor_x = user.x  # Start at player's position
        game_instance.targeting_cursor_y = user.y

        return True

    def execute_on_target(self, user, game_instance, target_x, target_y):
        """
        Performs the Mage Hand effect on the selected target.
        """
        target_tile = game_instance.game_map.tiles[target_y][target_x]

        # Create a temporary MageHandEntity instance to act as the 'player' for the trap trigger
        mage_hand_actor = MageHandEntity(user.x, user.y, user)  # Pass user as owner

        # Check if the target is a TrapTile
        if isinstance(target_tile, TrapTile) and not target_tile.trap_instance.is_triggered:
            game_instance.message_log.add_message(f"The Mage Hand triggers the {target_tile.trap_instance.name}!", (255, 255, 0))
            target_tile.trap_instance.trigger(mage_hand_actor, game_instance, target_x, target_y)  # Pass the mage_hand_actor
            return True  # Action successful, end turn

        # Check if the target is an item (specifically a potion)
        item_at_target = game_instance.get_interactable_item_at(target_x, target_y)
        if item_at_target and (isinstance(item_at_target, Potion) or isinstance(item_at_target, Food) or isinstance(item_at_target, OffHand)):
            # Instead of using mage_hand_actor, add the potion directly to the user's inventory
            if item_at_target.on_pickup(user, game_instance):  # Use the actual user as the picker
                game_instance.message_log.add_message(f"The Mage Hand picks up the {item_at_target.name}!", (0, 255, 0))
                # Remove the item from the ground after successful pickup
                game_instance.game_map.items_on_ground.remove(item_at_target)  # <-- Remove from ground
                return True  # Action successful, end turn
            else:
                game_instance.message_log.add_message(f"The Mage Hand cannot pick up the {item_at_target.name}.", (255, 150, 0))
                return False  # Failed to pick up the item

        game_instance.message_log.add_message("Mage Hand cannot interact with that target.", (255, 150, 0))
        return False  # Invalid target, stay in targeting mode


class RayOfFrost(Ability):
    def __init__(self):
        super().__init__("Ray of Frost", "Hurl a chilling ray of frost at a foe.", cost=0, cooldown=2)
        self.range = 6  # Example range in tiles
        self.damage_dice = 1 # Initial damage dice (e.g., 1d8)

    def use(self, user, game_instance):
        if not super().use(user, game_instance):
            return False

        # Helper: footprint-aware visibility
        def is_entity_visible(ent):
            allowed = ['player', 'torch', 'darkvision']
            size = getattr(ent, 'footprint_size', 1)
            if size > 1:
                for oy in range(size):
                    for ox in range(size):
                        if game_instance.fov.get_visibility_type(ent.x + ox, ent.y + oy) in allowed:
                            return True
                return False
            return game_instance.fov.get_visibility_type(ent.x, ent.y) in allowed

        # Helper: footprint-aware distance (min distance to any occupied tile)
        def distance_to_entity(ent):
            size = getattr(ent, 'footprint_size', 1)
            if size > 1:
                best = None
                for oy in range(size):
                    for ox in range(size):
                        d = user.distance_to(ent.x + ox, ent.y + oy)
                        if best is None or d < best:
                            best = d
                return best if best is not None else 9999
            return user.distance_to(ent.x, ent.y)

        # Find only monster targets within range (footprint-aware)
        monster_targets = []
        for entity in game_instance.entities:
            if isinstance(entity, Monster) and entity.alive:
                distance = distance_to_entity(entity)
                if distance <= self.range:  # Check against ability range
                    if is_entity_visible(entity):  # Footprint-aware FOV
                        monster_targets.append(entity)
        # If there are monster targets, auto-target the closest one
        if monster_targets:
            target = min(monster_targets, key=lambda m: user.distance_to(m.x, m.y))

            # Set the game state to targeting mode
            game_instance.game_state = GameState.TARGETING
            game_instance.ability_in_use = self  # Store which ability is being used
            game_instance.targeting_ability_range = self.range

            # Initialize targeting cursor at the auto-selected monster's position
            game_instance.targeting_cursor_x = target.x
            game_instance.targeting_cursor_y = target.y

            game_instance.message_log.add_message(f"{user.name} prepares Ray of Frost! Auto-targeting {target.name}.", (0, 255, 255))
            return True  # Indicate successful initiation of targeting

        # If no monster targets are found, revert to manual targeting starting at player
        else:
            game_instance.message_log.add_message(f"{user.name} prepares Ray of Frost! No enemies in range.).", (0, 255, 255))
            game_instance.game_state = GameState.TARGETING
            game_instance.ability_in_use = self  # Store which ability is being used
            game_instance.targeting_ability_range = self.range

            # Initialize targeting cursor at player's position
            game_instance.targeting_cursor_x = user.x
            game_instance.targeting_cursor_y = user.y

            return True  # Indicate successful initiation of targeting

    def execute_on_target(self, user, game_instance, target_x, target_y):
        """
        Performs the Ray of Frost effect on the selected target.
        """
        target_monster = game_instance.get_target_at(target_x, target_y)
        target_tile = game_instance.game_map.tiles[target_y][target_x]  # Get the tile object at target

        # Check if the target is within the player's FOV (tile or any tile of monster footprint)
        if not game_instance.fov.get_visibility_type(target_x, target_y) in ['player', 'torch', 'darkvision']:
            game_instance.message_log.add_message(f"You cannot attack {target_x}, {target_y} because it is out of sight!", (255, 0, 0))
            return False  # Do not consume a turn

        if not game_instance.check_line_of_sight(user.x, user.y, target_x, target_y):
            game_instance.message_log.add_message(f"A wall blocks your shot to {target_x}, {target_y}!", (255, 0, 0))
            return False # Do not consume a turn

        target_monster = game_instance.get_target_at(target_x, target_y)
        target_tile = game_instance.game_map.tiles[target_y][target_x]  # Get the tile object at target


        # Check if the target is a valid monster or destructible object
        if not (target_monster or target_tile.destructible):
            game_instance.message_log.add_message("Ray of Frost requires a monster target or a destructible object.", (255, 150, 0))
            return False  # Invalid target, do not consume a turn

        # Ray of Frost damage calculation (Xd8 cold damage)
        # Use self.damage_dice for the number of d8s
        damage_rolls = [random.randint(1, 8) for _ in range(self.damage_dice)]
        total_damage = sum(damage_rolls)

        game_instance.message_log.add_message(f"You roll {self.damage_dice}d8 for damage: {damage_rolls} = {total_damage}", (255, 100, 0))

        if target_monster and isinstance(target_monster, Monster):
            # Check if the target is specifically a Mimic
            hit_messages = [
                f"A chilling ray of frost streaks towards the {target_monster.name}!",
                f"Frost erupts as your spell connects with the {target_monster.name}!",
                f"The {target_monster.name} is engulfed in magical frost!",
            ]
            game_instance.message_log.add_message(random.choice(hit_messages), (0, 255, 255))

            if isinstance(target_monster, Mimic):
                damage_dealt = target_monster.take_damage(total_damage, game_instance, damage_type='cold')
            else:
                damage_dealt = target_monster.take_damage(total_damage, game_instance, damage_type='cold')  # Pass game_instance here

            game_instance.message_log.add_message(f"A ray of frost strikes {target_monster.name} for {damage_dealt} cold damage!", (0, 255, 255))
            game_instance.message_log.add_message(f"{target_monster.name} has {target_monster.hp}/{target_monster.max_hp} HP", (0, 255, 255))

            # Add FloatingText for "HIT!" and damage dealt
            hit_text = FloatingText(target_monster.x, target_monster.y, "HIT!", (0, 255, 255))
            game_instance.floating_texts.append(hit_text)

            damage_text = FloatingText(target_monster.x, target_monster.y - 0.5, str(damage_dealt), (0, 0, 255))  # <--- ADJUSTED Y
            game_instance.floating_texts.append(damage_text)

            if not target_monster.alive:
                xp_gained = target_monster.die(game_instance, killer=user)
                user.gain_xp(xp_gained, game_instance)  # Use 'user' (player) here
            return True  # Successfully used ability

        elif target_tile.destructible:  # <--- NEW: Check if the tile is destructible
            destructible_messages = [
                f"Your Ray of Frost freezes the {target_tile.name}!",
                f"A magical blizzard consumes the {target_tile.name}!",
            ]
            game_instance.message_log.add_message(random.choice(destructible_messages), (0, 255, 255))

            # For simplicity, we'll assume Ray of Frost instantly destroys destructible tiles
            # In a more complex system, destructible tiles might have HP.
            game_instance.message_log.add_message(f"Your Ray of Frost smashes the {target_tile.name}!", (0, 255, 255))
            game_instance.game_map.tiles[target_y][target_x] = floor  # Replace with floor tile
            self.minimap_needs_redraw = True # Map changed, redraw minimap

            # --- 10% chance to drop a healing potion ---
            if target_tile.name in ["Crate", "Barrel"]: # Check if it was a crate or barrel
                if random.random() < 0.70:
                    new_junk = wood_plank.__class__(
                        name=wood_plank.name,
                        char=wood_plank.char,
                        color=wood_plank.color,
                        description=wood_plank.description
                    )
                    new_junk.x = target_x
                    new_junk.y = target_y
                    game_instance.game_map.items_on_ground.append(new_junk)
                elif random.random() < 0.3:
                    new_torch = torch.__class__(
                        name=torch.name,
                        char=torch.char,
                        color=torch.color,
                        description=torch.description,
                        price=torch.price
                    )
                    new_torch.x = target_x
                    new_torch.y = target_y
                    game_instance.game_map.items_on_ground.append(new_torch)
                    game_instance.message_log.add_message(f"A {new_torch.name} drops from the {target_tile.name}!", new_torch.color)
                elif random.random() < 0.2:
                    new_food = meat.__class__(
                        name=meat.name,
                        char=meat.char,
                        color=meat.color,
                        description=meat.description,
                        healing_value=meat.healing_value,
                        price=meat.price
                    )
                    new_food.x = target_x
                    new_food.y = target_y
                    game_instance.game_map.items_on_ground.append(new_food)
                    game_instance.message_log.add_message(f"A {new_food.name} drops from the {target_tile.name}!", new_food.color)
                elif random.random() < 0.35:
                    new_food = green_apple.__class__(
                        name=green_apple.name,
                        char=green_apple.char,
                        color=green_apple.color,
                        description=green_apple.description,
                        healing_value=green_apple.healing_value,
                        price=green_apple.price
                    )
                    new_food.x = target_x
                    new_food.y = target_y
                    game_instance.game_map.items_on_ground.append(new_food)
                    game_instance.message_log.add_message(f"A {new_food.name} drops from the {target_tile.name}!", new_food.color)
                elif random.random() < 0.25:
                    new_food = fromage.__class__(
                        name=fromage.name,
                        char=fromage.char,
                        color=fromage.color,
                        description=fromage.description,
                        healing_value=fromage.healing_value,
                        price=fromage.price
                    )
                    new_food.x = target_x
                    new_food.y = target_y
                    game_instance.game_map.items_on_ground.append(new_food)
                    game_instance.message_log.add_message(f"A {new_food.name} drops from the {target_tile.name}!", new_food.color)
                elif random.random() < 0.3:
                    new_food = bread.__class__(
                        name=bread.name,
                        char=bread.char,
                        color=bread.color,
                        description=bread.description,
                        healing_value=bread.healing_value,
                        price=bread.price
                    )
                    new_food.x = target_x
                    new_food.y = target_y
                    game_instance.game_map.items_on_ground.append(new_food)
                    game_instance.message_log.add_message(f"A {new_food.name} drops from the {target_tile.name}!", new_food.color)
                elif random.random() < 0.4:
                    new_food = mushroom.__class__(
                        name=mushroom.name,
                        char=mushroom.char,
                        color=mushroom.color,
                        description=mushroom.description,
                        healing_value=mushroom.healing_value,
                        price=mushroom.price
                    )
                    new_food.x = target_x
                    new_food.y = target_y
                    game_instance.game_map.items_on_ground.append(new_food)
                    game_instance.message_log.add_message(f"A {new_food.name} drops from the {target_tile.name}!", new_food.color)


            # --- MISSING FLOATING TEXT CREATION HERE FOR DESTRUCTIBLE ---
            game_instance.floating_texts.append(FloatingText(target_x, target_y, "SMASH!", (0, 255, 255)))
            print(f"DEBUG: RayOfFrost added SMASH! FloatingText for {target_tile.name} at ({target_x},{target_y}). List size: {len(game_instance.floating_texts)}")  # <--- ADD THIS DEBUG

            # If it was a MimicTile, ensure the Mimic entity is also handled
            if isinstance(target_tile, MimicTile):
                mimic_entity = target_tile.mimic_entity
                if mimic_entity.disguised:
                    mimic_entity.reveal(game_instance)  # Reveal the mimic
                else:
                    game_instance.message_log.add_message(f"The {mimic_entity.name} is already revealed and takes no further damage from smashing its disguise.", (150, 150, 150))
            return True  # Successfully used ability
        else:
            game_instance.message_log.add_message("Ray of Frost requires a monster target or a destructible object.", (255, 150, 0))
            # --- MISSING FLOATING TEXT FOR MISS/INVALID TARGET ---
            game_instance.floating_texts.append(FloatingText(target_x, target_y, "INVALID!", (255, 0, 0)))
            print(f"DEBUG: RayOfFrost added INVALID! FloatingText for ({target_x},{target_y}). List size: {len(game_instance.floating_texts)}")  # <--- ADD THIS DEBUG
            return False  # Invalid target, stay in targeting mode

    def scale_with_level(self, player_level):
        """
        Scales the Ray of Frost ability with player level.
        Increases damage dice by 1 for every 4 levels (e.g., 1d8 at level 1, 2d8 at level 5, etc.)
        """
        additional_dice = (player_level - 1) // 5 # One extra die every 4 levels
        self.damage_dice = 1 + additional_dice

        print(f"[DEBUG] {self.name} scaled: damage_dice = {self.damage_dice} at player level {player_level}")        


class ActionSurge(Ability):
    def __init__(self):
        super().__init__("Action Surge", "Gain an additional action on your turn.", cooldown=20)
        self.extra_turns = 2

    def use(self, user, game_instance):
        if not super().use(user, game_instance):
            return False
        
        game_instance.message_log.add_message(f"{user.name} uses Action Surge!", (255, 255, 0))
        user.extra_turns = self.extra_turns
        
        user.add_status_effect("ActionSurgeEffect", duration=user.extra_turns + 1, game_instance=game_instance)
                
        # Using the ability is a valid action that ends the current phase.
        # The new logic in game.update() will catch the flag and grant the next turn.
        return True
    
    def scale_with_level(self, player_level):
        """
        Scales the Action Surge ability with player level.
        Reduces cooldown by 1 turn for every 6 levels and grants additional extra turn every 10 levels.
        """
        cooldown_reduction = (player_level - 2) // 6  # One less turn of cooldown every 6 levels
        self.cooldown = max(10, 20 - cooldown_reduction)  # Minimum cooldown of 10 turns
        self.extra_turns = 2 + (player_level - 1) // 10  # Gain an extra turn every 10 levels

        print(f"[DEBUG] {self.name} scaled: cooldown = {self.cooldown}, extra_turns = {self.extra_turns} at player level {player_level}")

    

class CunningActionHide(Ability):
    def __init__(self):
        super().__init__("Cunning Action: Hide", "Use a bonus action to Hide.", cooldown=39)

    def use(self, user, game_instance):
        if not super().use(user, game_instance):
            return False
        
        # Check if the player is already hidden
        user.hidden_turns = 6
        
        user.add_status_effect("Hidden", duration=user.hidden_turns + 1, game_instance=game_instance)

        game_instance.floating_texts.append(FloatingText(user.x, user.y, "HIDDEN!", (150, 150, 180)))
               
        
        return True  # Indicate successful use and end turn
    
    def scale_with_level(self, player_level):
        """
        Scales the Cunning Action: Hide ability with player level.
        Reduces cooldown by 1 turn for every 5 levels (e.g., 39 turns at level 1, 38 at level 6, etc.)
        """
        cooldown_reduction = (player_level - 2) // 5 # One less turn of cooldown every 5 levels
        self.cooldown = max(15, 39 - cooldown_reduction) # Minimum cooldown of 15 turns

        print(f"[DEBUG] {self.name} scaled: cooldown = {self.cooldown} at player level {player_level}")


class SummonImp(Ability):
    def __init__(self):
        super().__init__("Summon Imp", "Conjure a small imp to fight alongside you for 1 minute.", cooldown=20)
        self.imp_max_hp = 10
        self.imp_attack_power = 2
        self.imp_proficiency_bonus = 2

    def use(self, user, game_instance):
        if not self.can_use(user, game_instance):
            return False

        existing_imp = None
        for entity in game_instance.entities:
            if isinstance(entity, Imp) and entity.owner == user:
                existing_imp = entity
                break

        if existing_imp:
            game_instance.message_log.add_message(f"You dismiss your imp back to the Abyss.", (180, 180, 255))
            existing_imp.die(game_instance)
            return True

        # Systematically check all 8 adjacent tiles
        adjacent_offsets = [(0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)]
        
        for dx, dy in adjacent_offsets:
            new_x = user.x + dx
            new_y = user.y + dy
            
            # Check if the spot is walkable
            if game_instance.game_map.is_walkable(new_x, new_y):
                # Check if blocked by another entity
                blocked = False
                for entity in game_instance.entities:
                    if entity.x == new_x and entity.y == new_y and entity.blocks_movement:
                        blocked = True
                        break
                
                if not blocked:
                    # Summon the imp with scaled stats
                    imp = Imp(
                        new_x,
                        new_y,
                        user,
                        hp=self.imp_max_hp,
                        attack_power=self.imp_attack_power,
                        proficiency_bonus=self.imp_proficiency_bonus,
                    )
                    game_instance.entities.append(imp)
                    game_instance.turn_order.append(imp)
                    game_instance.message_log.add_message(f"A small imp materializes with a cackling laugh!", (180, 50, 50))
                    print(f"[DEBUG] Imp summoned at ({new_x}, {new_y}) for player at ({user.x}, {user.y})")
                    game_instance.update_fov()
                    return True

        game_instance.message_log.add_message(f"There's no room to summon an imp nearby!", (255, 150, 0))
        return False

    def scale_with_level(self, player_level):
        """
        Scales the Summon Imp ability with player level.
        Increases imp HP and damage as the caster gains levels.
        """
        self.imp_max_hp = 10 + max(0, (player_level - 1) // 2)
        self.imp_attack_power = 2 + max(0, (player_level - 1) // 4)
        self.imp_proficiency_bonus = 2 + max(0, (player_level - 1) // 5)

        print(
            f"[DEBUG] {self.name} scaled: imp_max_hp={self.imp_max_hp}, "
            f"attack_power={self.imp_attack_power}, proficiency_bonus={self.imp_proficiency_bonus} "
            f"at player level {player_level}"
        )


class CureWounds(Ability):
    def __init__(self):
        super().__init__("Cure Wounds", "Heal yourself or an ally within 2 tiles for 1d8 HP.", cooldown=16) # 16 turns cooldown
        self.range = 2
        self.healing_dice = 1

    def use(self, user, game_instance):
        # Call base class use to handle cooldown and initial checks.
        # If base.use returns False (because can_use failed), then this method should also return False.
        if not super().use(user, game_instance):
            return False
        
        # Find valid targets (player and friendly allies within range)
        valid_targets = []
        for entity in game_instance.entities:
            if entity.alive and (entity == user or isinstance(entity, NPC)):
                distance = user.distance_to(entity.x, entity.y)
                if distance <= self.range:
                    valid_targets.append(entity)

        if not valid_targets:
            game_instance.message_log.add_message("No valid targets for Cure Wounds within range.", (255, 150, 0))
            return False

        # If there are valid targets, enter targeting mode
        game_instance.message_log.add_message(f"{user.name} prepares to cast Cure Wounds!).", (0, 255, 255))
        game_instance.message_log.add_message(f"Select a target to heal", (0, 255, 255))
        game_instance.game_state = GameState.TARGETING
        game_instance.ability_in_use = self
        game_instance.targeting_ability_range = self.range
        game_instance.targeting_cursor_x = user.x
        game_instance.targeting_cursor_y = user.y

        return True

    def execute_on_target(self, user, game_instance, target_x, target_y):
        """Apply Cure Wounds to the chosen target."""
        if user.x == target_x and user.y == target_y:
            target = user
        else:
            target = game_instance.get_target_at(target_x, target_y)

        if not target or not target.alive or not (target == user or isinstance(target, NPC)):
            game_instance.message_log.add_message("Cure Wounds can only be cast on yourself or a friendly ally.", (255, 150, 0))
            return False

        heal_rolls = [random.randint(1, 8) for _ in range(self.healing_dice)]
        total_heal = sum(heal_rolls)
        old_hp = getattr(target, 'hp', 0)

        if hasattr(target, 'heal'):
            healed_amount = target.heal(total_heal)
        else:
            target.hp = min(target.max_hp, target.hp + total_heal)
            healed_amount = target.hp - old_hp

        game_instance.message_log.add_message(f"You cast Cure Wounds on {target.name}", (0, 255, 0))
        game_instance.message_log.add_message(f"You roll {self.healing_dice}d8 for healing: {heal_rolls} = {total_heal}", (0, 255, 0))
        game_instance.message_log.add_message(f"Healed for {healed_amount} HP.", (0, 255, 0))
        game_instance.floating_texts.append(FloatingText(target.x, target.y, f"{healed_amount}", (0, 255, 0)))
        return True
    
    def scale_with_level(self, player_level):
        """
        Scales the Cure Wounds ability with player level.
        Increases healing dice by 1 for every 4 levels (e.g., 1d8 at level 1, 2d8 at level 5, etc.)
        """
        additional_dice = (player_level - 1) // 5 # One extra die every 4 levels
        self.healing_dice = 1 + additional_dice

        print(f"[DEBUG] {self.name} scaled: healing_dice = {self.healing_dice} at player level {player_level}")


class HealingWord(Ability):
    def __init__(self):
        super().__init__("Healing Word", "Heal yourself or an ally within 6 tiles for 1d4 HP as a bonus action.", cooldown=16)
        self.range = 6
        self.healing_dice = 1
        self.is_bonus_action = True  # This ability can be used as a bonus action

    def use(self, user, game_instance):
        if not super().use(user, game_instance):
            return False
        
        # Find valid targets (player and friendly allies within range)
        valid_targets = []
        for entity in game_instance.entities:
            if entity.alive and (entity == user or isinstance(entity, NPC)):
                distance = user.distance_to(entity.x, entity.y)
                if distance <= self.range:
                    valid_targets.append(entity)

        if not valid_targets:
            game_instance.message_log.add_message("No valid targets for Healing Word within range.", (255, 150, 0))
            return False

        # If there are valid targets, enter targeting mode
        game_instance.message_log.add_message(f"{user.name} prepares to cast Healing Word!", (0, 255, 255))
        game_instance.message_log.add_message("Select a target to heal", (0, 255, 255))
        game_instance._previous_game_state = game_instance.game_state
        game_instance.game_state = GameState.TARGETING
        game_instance.ability_in_use = self
        game_instance.targeting_ability_range = self.range
        game_instance.targeting_cursor_x = user.x
        game_instance.targeting_cursor_y = user.y

        return True
    
    def execute_on_target(self, user, game_instance, target_x, target_y):
        """Apply Healing Word to the chosen target."""
        if user.x == target_x and user.y == target_y:
            target = user
        else:
            target = game_instance.get_target_at(target_x, target_y)

        if not target or not target.alive or not (target == user or isinstance(target, NPC)):
            game_instance.message_log.add_message("Healing Word can only be cast on yourself or a friendly ally.", (255, 150, 0))
            return False

        heal_rolls = [random.randint(1, 4) for _ in range(self.healing_dice)]
        total_heal = sum(heal_rolls)
        old_hp = getattr(target, 'hp', 0)

        if hasattr(target, 'heal'):
            healed_amount = target.heal(total_heal)
        else:
            target.hp = min(target.max_hp, target.hp + total_heal)
            healed_amount = target.hp - old_hp

        game_instance.floating_texts.append(FloatingText(target.x, target.y, f"{healed_amount}", (0, 255, 0)))

        game_instance.message_log.add_message(f"You cast Healing Word on {target.name}", (0, 255, 0))
        game_instance.message_log.add_message(f"You roll {self.healing_dice}d4 for healing: {heal_rolls} = {total_heal}", (0, 255, 0))
        game_instance.message_log.add_message(f"Healed for {healed_amount} HP", (0, 255, 0))
        return True

    def scale_with_level(self, player_level):
        """
        Scales the Healing Word ability with player level.
        Increases healing dice by 1 for every 4 levels (e.g., 1d4 at level 1, 2d4 at level 5, etc.)
        """
        additional_dice = (player_level - 1) // 5 # One extra die every 4 levels
        self.healing_dice = 1 + additional_dice

        print(f"[DEBUG] {self.name} scaled: healing_dice = {self.healing_dice} at player level {player_level}")


class SacredFlame(Ability):
    def __init__(self):
        super().__init__("Sacred Flame", "Call down a radiant flame to damage an enemy within 6 tiles.", cost=0, cooldown=2)
        self.range = 6
        self.damage_dice = 1

    def use(self, user, game_instance):
        if not super().use(user, game_instance):
            return False

        # Find valid targets (enemies within range)
        monster_targets = []
        for entity in game_instance.entities:
            if isinstance(entity, Monster) and entity.alive:
                distance = user.distance_to(entity.x, entity.y)
                if distance <= self.range:
                    monster_targets.append(entity)

        if not monster_targets:
            game_instance.message_log.add_message("No valid targets for Sacred Flame within range.", (255, 150, 0))
            return False

        # If there are monster targets, auto-target the closest one
        target = min(monster_targets, key=lambda m: user.distance_to(m.x, m.y))

        # Set the game state to targeting mode
        game_instance.game_state = GameState.TARGETING
        game_instance.ability_in_use = self
        game_instance.targeting_ability_range = self.range

        # Initialize targeting cursor at the auto-selected monster's position
        game_instance.targeting_cursor_x = target.x
        game_instance.targeting_cursor_y = target.y

        game_instance.message_log.add_message(f"{user.name} prepares Sacred Flame! Auto-targeting {target.name}.", (255, 255, 0))
        return True
    
    def execute_on_target(self, user, game_instance, target_x, target_y):
        target = game_instance.get_target_at(target_x, target_y)

        if not target or not isinstance(target, Monster) or not target.alive:
            game_instance.message_log.add_message("Sacred Flame can only be cast on an enemy.", (255, 150, 0))
            return False

        damage_rolls = [random.randint(1, 8) for _ in range(self.damage_dice)]
        total_damage = sum(damage_rolls)

        # All targets must roll a Dexterity saving throw (DC 10)
        dex_modifier = 0
        if hasattr(target, 'dexterity'):
            dex_modifier = (target.dexterity - 10) // 2
        
        # Add proficiency bonus if the target has proficiency in DEX saves
        if target.saving_throw_proficiencies.get('DEX', False):
            proficiency_bonus = getattr(target, 'proficiency_bonus', 0)
            dex_modifier += proficiency_bonus
        
        save_roll = random.randint(1, 20) + dex_modifier
        dc = 10
        
        if save_roll >= dc:
            total_damage //= 2
            game_instance.message_log.add_message(f"{target.name} makes a Dexterity saving throw (rolled {save_roll}, DC {dc})! Damage is halved to {total_damage}.", (255, 255, 0))
        else:
            game_instance.message_log.add_message(f"{target.name} fails the Dexterity saving throw (rolled {save_roll}, DC {dc})! Full damage applies.", (255, 255, 0))

        game_instance.message_log.add_message(f"You roll {self.damage_dice}d8 for damage: {damage_rolls} = {total_damage}", (255, 100, 0))

        damage_dealt = target.take_damage(total_damage, game_instance, damage_type='radiant')

        hit_text = FloatingText(target.x, target.y, "HIT!", (220, 220, 0))
        game_instance.floating_texts.append(hit_text)

        damage_text = FloatingText(target.x, target.y - 0.5, str(damage_dealt), (220, 220, 0))  # <--- ADJUSTED Y
        game_instance.floating_texts.append(damage_text)


        game_instance.message_log.add_message(f"A sacred flame strikes {target.name} for {damage_dealt} radiant damage!", (255, 255, 0))
        game_instance.message_log.add_message(f"{target.name} has {target.hp}/{target.max_hp} HP", (255, 255, 0))

        if not target.alive:
            xp_gained = target.die(game_instance, killer=user)
            user.gain_xp(xp_gained, game_instance)
        return True
    
    def scale_with_level(self, player_level):
        """
        Scales the Sacred Flame ability with player level.
        Increases damage dice by 1 for every 4 levels (e.g., 1d8 at level 1, 2d8 at level 5, etc.)
        """
        additional_dice = (player_level - 1) // 5 # One extra die every 4 levels
        self.damage_dice = 1 + additional_dice

        print(f"[DEBUG] {self.name} scaled: damage_dice = {self.damage_dice} at player level {player_level}")


class SummonCelestial(Ability):
    def __init__(self):
        super().__init__("Summon Celestial", "Summon a powerful celestial ally to fight for you for 1 minute.", cooldown=30)
        self.celestial_max_hp = 20
        self.celestial_attack_power = 5
        self.celestial_proficiency_bonus = 3

    def use(self, user, game_instance):
        if not self.can_use(user, game_instance):
            return False

        existing_celestial = None
        for entity in game_instance.entities:
            if isinstance(entity, Celestial) and entity.owner == user:
                existing_celestial = entity
                break

        if existing_celestial:
            game_instance.message_log.add_message(f"You dismiss your celestial back to the heavens.", (200, 200, 255))
            existing_celestial.die(game_instance)
            return True

        adjacent_offsets = [(0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)]
        
        for dx, dy in adjacent_offsets:
            new_x = user.x + dx
            new_y = user.y + dy
            
            if game_instance.game_map.is_walkable(new_x, new_y):
                blocked = False
                for entity in game_instance.entities:
                    if entity.x == new_x and entity.y == new_y and entity.blocks_movement:
                        blocked = True
                        break
                
                if not blocked:
                    celestial = Celestial(
                        new_x,
                        new_y,
                        user,
                        hp=self.celestial_max_hp,
                        attack_power=self.celestial_attack_power,
                        proficiency_bonus=self.celestial_proficiency_bonus,
                    )
                    game_instance.entities.append(celestial)
                    game_instance.turn_order.append(celestial)
                    game_instance.message_log.add_message(f"A radiant celestial descends from the heavens to aid you!", (200, 200, 255))
                    print(f"[DEBUG] Celestial summoned at ({new_x}, {new_y}) for player at ({user.x}, {user.y})")
                    game_instance.update_fov()
                    return True

        game_instance.message_log.add_message(f"There's no room to summon a celestial nearby!", (255, 150, 0))
        return False
    
    def scale_with_level(self, player_level):
        """
        Scales the Summon Celestial ability with player level.
        Increases celestial HP and damage as the caster gains levels.
        """
        self.celestial_max_hp = 20 + max(0, (player_level - 1) // 2)
        self.celestial_attack_power = 5 + max(0, (player_level - 1) // 4)
        self.celestial_proficiency_bonus = 3 + max(0, (player_level - 1) // 5)

        print(
            f"[DEBUG] {self.name} scaled: celestial_max_hp={self.celestial_max_hp}, "
            f"attack_power={self.celestial_attack_power}, proficiency_bonus={self.celestial_proficiency_bonus} "
            f"at player level {player_level}"
        )


class DivineStrike(Ability):
    def __init__(self):
        super().__init__("Divine Strike", "Your weapon attacks deal an extra 1d8 radiant damage on a hit.", cooldown=10)
        self.extra_damage_dice = 1

    def use(self, user, game_instance):
        if not super().use(user, game_instance):
            return False
        
        user.add_status_effect("DivineStrikeBuff", duration=3, game_instance=game_instance)
        game_instance.message_log.add_message(f"{user.name} empowers their weapon with divine energy!", (255, 255, 0))
        return True
    
    def scale_with_level(self, player_level):
        """
        Scales the Divine Strike ability with player level.
        Increases extra damage dice by 1 for every 4 levels (e.g., 1d8 at level 1, 2d8 at level 5, etc.)
        """
        additional_dice = (player_level - 1) // 5 # One extra die every 4 levels
        DivineStrikeBuff.base_extra_damage_dice = 1 + additional_dice

        print(f"[DEBUG] {self.name} scaled: extra_damage_dice = {DivineStrikeBuff.base_extra_damage_dice} at player level {player_level}")


class SpiritualWeapon(Ability):
    def __init__(self):
        super().__init__("Spiritual Weapon", "Summon a floating weapon that strikes a target within 5 tiles as a bonus action.", cooldown=10)
        self.spiritual_weapon_max_hp = 1
        self.spiritual_weapon_attack_power = 5
        self.spiritual_weapon_proficiency_bonus = 2

    def use(self, user, game_instance):
        if not super().use(user, game_instance):
            return False
        
        existing_weapon = None
        for entity in game_instance.entities:
            if isinstance(entity, SpiritualWeaponEntity) and entity.owner == user:
                existing_weapon = entity
                break

        if existing_weapon:
            game_instance.message_log.add_message(f"You dismiss your spiritual weapon.", (180, 180, 255))
            existing_weapon.die(game_instance)
            return True
        
        adjacent_offsets = [(0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)]

        for dx, dy in adjacent_offsets:
            new_x = user.x + dx
            new_y = user.y + dy
            
            if game_instance.game_map.is_walkable(new_x, new_y):
                blocked = False
                for entity in game_instance.entities:
                    if entity.x == new_x and entity.y == new_y and entity.blocks_movement:
                        blocked = True
                        break
                
                if not blocked:
                    spiritual_weapon = SpiritualWeaponEntity(
                        new_x,
                        new_y,
                        user,
                        hp=self.spiritual_weapon_max_hp,  # Spiritual weapon is a temporary entity that doesn't have HP in the traditional sense
                        attack_power=self.spiritual_weapon_attack_power,
                        proficiency_bonus=self.spiritual_weapon_proficiency_bonus,
                    )
                    game_instance.entities.append(spiritual_weapon)
                    game_instance.turn_order.append(spiritual_weapon)
                    game_instance.message_log.add_message(f"A shimmering spiritual weapon materializes and floats nearby!", (180, 180, 255))
                    print(f"[DEBUG] Spiritual Weapon summoned at ({new_x}, {new_y}) for player at ({user.x}, {user.y})")
                    game_instance.update_fov()
                    return True
                
        game_instance.message_log.add_message(f"There's no room to summon a spiritual weapon nearby!", (255, 150, 0))
        return False                
    
    def scale_with_level(self, player_level):
        """
        Scales the Spiritual Weapon ability with player level.
        Increases damage dice by 1 for every 4 levels (e.g., 1d8 at level 1, 2d8 at level 5, etc.)
        """
        additional_dice = (player_level - 1) // 5 # One extra die every 4 levels
        self.damage_dice = 1 + additional_dice

        print(f"[DEBUG] {self.name} scaled: damage_dice = {self.damage_dice} at player level {player_level}")