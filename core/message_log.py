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
        self.max_lines = height // self.line_height  # Number of lines visible

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
        self.scroll_offset = 0
        self.clamp_scroll_offset()

    def truncate_messages(self, max_messages):
        if len(self.messages) > max_messages:
            self.messages = self.messages[-max_messages:]
            self.scroll_offset = 0
            self.clamp_scroll_offset()

    def clear_last_input(self):
        """Clear the current input text."""
        self.current_input = ""

    def scroll_up(self):
        self.scroll_offset += 1
        self.clamp_scroll_offset()
    
    def scroll_down(self):
        self.scroll_offset -= 1
        self.clamp_scroll_offset()

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
        start_index = max(0, len(self.messages) - self.max_lines - self.scroll_offset)
        end_index = start_index + self.max_lines
        
        visible_messages = self.messages[start_index:end_index]
        
        y = self.rect.y
        for text, color in visible_messages:
            # Render text at (self.rect.x, y)
            text_surface = self.font.render(text, True, color)
            surface.blit(text_surface, (self.rect.x, y))
            y += self.line_height
        
        # Draw the input area only if the flag is set
        if self.show_input_area:
            input_surface = self.font.render(self.current_input, True, (255, 255, 255))
            input_y_position = self.rect.y + self.rect.height - self.input_height + 5  # Position input text above the bottom margin
            pygame.draw.rect(surface, (30, 30, 30), (self.rect.x, self.rect.y + self.rect.height - self.input_height, self.rect.width, self.input_height))  # Draw input area background
            surface.blit(input_surface, (self.rect.x + 5, input_y_position))  # Draw input text

    def clamp_scroll_offset(self):
        max_offset = max(0, len(self.messages) - self.max_lines)
        if self.scroll_offset < 0:
            self.scroll_offset = 0
        elif self.scroll_offset > max_offset:
            self.scroll_offset = max_offset

