import pygame
from pygame import Rect

class MessageBox:
    def __init__(self, x, y, width, height, font=None):
        self.rect = Rect(x, y, width, height)
        self.messages = []  # Now stores ALL messages
        self.scroll_offset = 0  # NEW: Tracks the scroll position (index of the first visible message)
        self.current_input = ""  # Store current input text
        self.input_height = 30  # Height reserved for input
        self.show_input_area = False  # Flag to control input area visibility
        if font is None:
            self.font = pygame.font.Font(None, 16)
        else:
            self.font = pygame.font.Font(font, 16)
        self.line_height = self.font.get_linesize()
        self.max_lines = (height // self.line_height) - 1  # Leave room for input

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
        self.scroll_offset = max(0, len(self.messages) - self.max_lines)

    def clear_last_input(self):
        """Clear the current input text."""
        self.current_input = ""

    def scroll_up(self):
        """Scrolls the message log up by one line."""
        if self.scroll_offset > 0:
            self.scroll_offset -= 1

    def scroll_down(self):
        """Scrolls the message log down by one line."""
        if self.scroll_offset < len(self.messages) - self.max_lines:
            self.scroll_offset += 1

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
        
        # Draw the input area only if the flag is set
        if self.show_input_area:
            input_surface = self.font.render(self.current_input, True, (255, 255, 255))
            input_y_position = self.rect.y + self.rect.height - self.input_height + 5  # Position input text above the bottom margin
            pygame.draw.rect(surface, (30, 30, 30), (self.rect.x, self.rect.y + self.rect.height - self.input_height, self.rect.width, self.input_height))  # Draw input area background
            surface.blit(input_surface, (self.rect.x + 5, input_y_position))  # Draw input text



