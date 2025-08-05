class StatusEffect:
    def __init__(self, name, duration, description=""):
        self.name = name
        self.duration = duration  # Duration in turns
        self.description = description
        self.turns_left = duration

    def apply(self, target, game_instance):
        """Called when the effect is first applied to the target."""
        game_instance.message_log.add_message(f"{target.name} is now {self.name}!", (255, 100, 0))
        # Override in subclasses for specific initial effects

    def tick(self, target, game_instance):
        """Called each turn the effect is active."""
        self.turns_left -= 1
        # Override in subclasses for specific per-turn effects

    def remove(self, target, game_instance):
        """Called when the effect is removed from the target."""
        game_instance.message_log.add_message(f"{target.name} is no longer {self.name}.", (100, 255, 0))
        # Override in subclasses for specific removal effects

    def __eq__(self, other):
        # Used to check if an effect of the same type is already active
        return isinstance(other, type(self)) and self.name == other.name

    def __hash__(self):
        return hash(self.name)

class Poisoned(StatusEffect):
    def __init__(self, duration=3, damage_per_turn=2):
        super().__init__("Poisoned", duration, f"Takes {damage_per_turn} damage per turn.")
        self.damage_per_turn = damage_per_turn

    def apply(self, target, game_instance):
        super().apply(target, game_instance)
        game_instance.message_log.add_message(f"{target.name} feels a burning sensation!", (255, 150, 0))

    def tick(self, target, game_instance):
        super().tick(target, game_instance)
        if target.alive:
            damage_dealt = target.take_damage(self.damage_per_turn)
            game_instance.message_log.add_message(f"{target.name} takes {damage_dealt} poison damage. ({self.turns_left} turns left)", (255, 0, 0))
            if not target.alive:
                game_instance.message_log.add_message(f"{target.name} succumbed to the poison!", (200, 0, 0))

    def remove(self, target, game_instance):
        super().remove(target, game_instance)
        game_instance.message_log.add_message(f"{target.name} shakes off the poison.", (150, 255, 150))

