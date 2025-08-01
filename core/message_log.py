# core/message_log.py
import pygame
from pygame import Rect

class MessageBox:
    def __init__(self, x, y, width, height, font=None, font_size=16):
        self.rect = Rect(x, y, width, height)
        self.messages = []
        if font is None:
            self.font = pygame.font.Font(None, font_size)
        else:
            self.font = pygame.font.Font(font, font_size)
        self.line_height = self.font.get_linesize()
        self.max_lines = height // self.line_height

    def add_message(self, text, color=None):
        """Add a new message to the log"""
        if color is None:
            color = (255, 255, 255)  # Default to white
            
        # Split long messages into multiple lines if needed
        words = text.split(' ')
        lines = []
        current_line = []
        
        for word in words:
            test_line = ' '.join(current_line + [word])
            if self.font.size(test_line)[0] <= self.rect.width - 20:  # 20px padding
                current_line.append(word)
            else:
                lines.append(' '.join(current_line))
                current_line = [word]
        if current_line:
            lines.append(' '.join(current_line))
            
        for line in lines:
            self.messages.append((line, color))
            
        # Keep log to max_lines
        self.messages = self.messages[-self.max_lines:]

    def render(self, surface):
        """Render the message log to the given surface"""
        # Draw background
        pygame.draw.rect(surface, (0, 0, 0), self.rect)
        pygame.draw.rect(surface, (255, 255, 255), self.rect, 2)

        # Render messages
        y_offset = 5  # Padding from top
        for msg, color in self.messages:
            text_surface = self.font.render(msg, True, color)
            surface.blit(text_surface, (self.rect.x + 5, self.rect.y + y_offset))
            y_offset += self.line_height
