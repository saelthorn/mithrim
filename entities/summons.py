from entities.base_entity import NPC # Reusing NPC as a base for simplicity

class SummonedEntity(NPC):
    """
    Base class for any entity summoned by a player ability.
    """
    def __init__(self, x, y, char, name, color, owner, duration=0):
        super().__init__(x, y, char, name, color)
        self.owner = owner  # The player or entity that summoned this
        self.duration = duration # How many turns the summon lasts (0 for permanent until destroyed)
        self.turns_left = duration
        self.blocks_movement = True # Most summons block movement
        self.alive = True # Summons start alive
        self.hp = 1 # Summons might have very low HP or be invulnerable
        self.max_hp = 1
        self.attack_power = 0 # Most summons don't attack by default
        self.armor_class = 0 # Most summons don't have AC by default

    def take_turn(self, player, game_map, game):
        """
        Summoned entities might have their own AI or simply expire.
        This method should be overridden by specific summons.
        """
        self.tick_duration(game)
        if not self.alive:
            return

        # Default behavior: do nothing or move randomly
        # Specific summons (like a combat pet) would have their own logic here.
        pass

    def tick_duration(self, game_instance):
        """Decrements the summon's duration each turn."""
        if self.duration > 0:
            self.turns_left -= 1
            if self.turns_left <= 0:
                self.die(game_instance)

    def die(self, game_instance):
        """Handles the summon's despawn or death."""
        self.alive = False
        game_instance.message_log.add_message(f"The {self.name} vanishes!", self.color)
        # Remove from entities list and turn order
        if self in game_instance.entities:
            game_instance.entities.remove(self)
        if self in game_instance.turn_order:
            game_instance.turn_order.remove(self)
        game_instance.update_fov() # Update FOV if it was a light source or blocking sight


class MageHandEntity(SummonedEntity):
    """
    A spectral hand summoned by the Mage Hand ability.
    It's primarily for interaction, not combat.
    """
    def __init__(self, x, y, owner):
        # Mage Hand is typically invisible or translucent, but for display, use a char.
        # It doesn't have HP or take damage in D&D 5e, so HP is set to 1 as a placeholder.
        super().__init__(x, y, 'mh', 'Mage Hand', (150, 200, 255), owner, duration=10) # Lasts 1 minute (10 turns)
        self.blocks_movement = False # Mage Hand typically doesn't block movement
        self.hp = 1 # It's not a combatant, so effectively invulnerable to damage
        self.max_hp = 1
        self.armor_class = 0 # No AC, as it's not directly targetable by attacks

    def take_damage(self, amount, game_instance=None, damage_type=None):
        """
        Mage Hand does not take damage. Override to prevent HP reduction.
        """
        # Log that it was "hit" but took no damage
        if game_instance:
            game_instance.message_log.add_message(f"The {self.name} shimmers but is unaffected.", self.color)
        return 0 # No damage taken

    def take_turn(self, player, game_map, game):
        """
        Mage Hand doesn't have an active turn in the initiative order.
        Its actions are controlled directly by the player's ability use.
        However, its duration still ticks down.
        """
        self.tick_duration(game)
        # No other actions for Mage Hand on its "turn"
        pass

    def die(self, game_instance):
        """Handles the Mage Hand vanishing."""
        self.alive = False
        game_instance.message_log.add_message(f"The {self.name} dissipates.", self.color)
        if self in game_instance.entities:
            game_instance.entities.remove(self)
        if self in game_instance.turn_order:
            game_instance.turn_order.remove(self)
        # No FOV update needed as it's not a light source and doesn't block sight.

