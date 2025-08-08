
class StatusEffect:
    def __init__(self, name, duration, source=None):
        self.name = name
        self.duration = duration
        self.turns_left = duration
        self.source = source # Who applied the effect (e.g., a monster)

    def apply_effect(self, target, game_instance):
        """Applies the effect to the target each turn."""
        pass # To be overridden by specific effects

    def tick_down(self):
        """Decrements the duration of the effect."""
        self.turns_left -= 1

    def on_end(self, target, game_instance):
        """Called when the effect ends."""
        game_instance.message_log.add_message(f"{target.name} is no longer {self.name.lower()}.", (150, 150, 150))

class Poisoned(StatusEffect):
    def __init__(self, duration, source=None, damage_per_turn=2): # <--- ADD damage_per_turn here
        super().__init__("Poisoned", duration, source)
        self.damage_per_turn = damage_per_turn # <--- Assign it here
    
    def apply_effect(self, target, game_instance):
        if self.turns_left > 0:
            game_instance.message_log.add_message(f"{target.name} is poisoned! Takes {self.damage_per_turn} damage.", (255, 0, 0))
            target.take_damage(self.damage_per_turn)
            
            if not target.alive:
                game_instance.message_log.add_message(f"{target.name} succumbed to poison!", (200, 0, 0))
    
    def on_end(self, target, game_instance):
        super().on_end(target, game_instance)
