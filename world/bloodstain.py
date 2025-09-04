

class Bloodstain:
    def __init__(self, x, y, game_instance, duration=20):
        self.x = x
        self.y = y
        self.duration = duration  # Total turns the bloodstain will last
        self.turns_left = duration
        self.expired = False
        self.char = 'bl' # Character to represent bloodstain (e.g., a splatter)
        self.color = (150, 0, 0) # Base color for bloodstain

    def tick_down(self):
        """Decrements the bloodstain's duration."""
        self.turns_left -= 1
        if self.turns_left <= 0:
            self.expired = True
