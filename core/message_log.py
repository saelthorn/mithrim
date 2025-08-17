# MultipleFiles/message_log.py
import pygame
from pygame import Rect

class MessageBox:
    def __init__(self, x, y, width, height, font=None):
        self.rect = Rect(x, y, width, height)
        self.messages = [] # Now stores ALL messages
        self.scroll_offset = 0 # NEW: Tracks the scroll position (index of the first visible message)
        
        if font is None:
            self.font = pygame.font.Font(None, 16)
        else:
            self.font = pygame.font.Font(font, 16)

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
            
        # When a new message is added, automatically scroll to the bottom
        # This ensures the latest message is always visible
        self.scroll_offset = max(0, len(self.messages) - self.max_lines)

    def scroll_up(self, lines=1):
        """Scrolls the message log up by a given number of lines."""
        self.scroll_offset = max(0, self.scroll_offset - lines)

    def scroll_down(self, lines=1):
        """Scrolls the message log down by a given number of lines."""
        # Ensure we don't scroll past the end of the messages
        self.scroll_offset = min(max(0, len(self.messages) - self.max_lines), self.scroll_offset + lines)

    def render(self, surface):
        """Render the message log to the given surface"""
        # Draw background
        pygame.draw.rect(surface, (0, 0, 0), self.rect)
        
        # Draw only the top border line
        pygame.draw.line(surface, (50, 50, 50), 
                         (self.rect.left, self.rect.top), 
                         (self.rect.right, self.rect.top), 
                         1)

        # Render messages
        y_offset = 5  # Padding from top
        # Only render messages within the current scroll view
        visible_messages = self.messages[self.scroll_offset : self.scroll_offset + self.max_lines]
        
        for msg, color in visible_messages:
            text_surface = self.font.render(msg, True, color)
            surface.blit(text_surface, (self.rect.x + 5, self.rect.y + y_offset))
            y_offset += self.line_height

