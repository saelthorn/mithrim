import pygame
from pygame import Rect


# ---------------------------------------------------------------------------
# Category detection helpers
# ---------------------------------------------------------------------------

def _detect_category(text: str, color: tuple) -> str:
    """
    Infer a message category from its content and color.
    Categories: 'combat', 'loot', 'ambient', 'system', 'danger', 'default'
    """
    t = text.lower()

    # Explicit system colors (cyan-ish or bright white headers)
    if color in [(0, 255, 255), (100, 255, 255), (240, 240, 240), (255, 255, 255)] and (
        "===" in text or "entered" in t or "welcome" in t or "level" in t
        or "restarting" in t or "dungeon" in t and "level" in t
    ):
        return "system"

    # Danger / death
    if color in [(255, 0, 0)] or any(
        kw in t for kw in ("you died", "you fall", "game over", "critical fumble",
                           "dead", "dying", "poison", "burning", "frozen")
    ):
        return "danger"

    # Combat keywords
    combat_kws = ("hit", "miss", "attack", "damage", "roll", "strike",
                  "wound", "slay", "kill", "stab", "slash", "crit",
                  "dodge", "block", "parry", "ac ", "hp", "d20",
                  "fumble", "opportunity", "sneak attack")
    if any(kw in t for kw in combat_kws):
        return "combat"

    # Loot / item keywords
    loot_kws = ("pick up", "pickup", "found", "chest", "drops",
                "gold", "potion", "sword", "axe", "armor", "shield",
                "dagger", "staff", "equip", "item", "inventory",
                "torch", "loot", "acquire", "you gain")
    if any(kw in t for kw in loot_kws):
        return "loot"

    # Ambient / flavor
    ambient_kws = ("dungeon", "silence", "echo", "creak", "drip",
                   "smell", "shadow", "dark", "cold", "warm",
                   "tavern", "fire", "bard", "hearth", "mug",
                   "shuffle", "skitter", "whisper", "groan",
                   "rat ", "torch flicker")
    if any(kw in t for kw in ambient_kws):
        return "ambient"

    return "default"


# Category visual config: (left_strip_color, default_text_color_override_or_None)
_CATEGORY_STYLE = {
    "combat":  ((200,  50,  50), None),
    "loot":    ((200, 170,   0), None),
    "ambient": (( 80,  80,  80), None),
    "system":  ((  0, 180, 220), None),
    "danger":  ((220,  30,  30), (255,  80,  80)),
    "default": (( 50,  50,  60), None),
}

# How many of the most-recent messages appear at full brightness
_FADE_RECENT_COUNT = 6
_FADE_MIN_ALPHA    = 55   # oldest visible messages render at this alpha (0-255)


class MessageBox:
    # Compact mode: smaller line height / font scale
    COMPACT_FONT_SIZE  = 13
    EXPANDED_FONT_SIZE = 15   # used when compact=False

    LEFT_STRIP_WIDTH   = 3    # px — colored category indicator on the left
    LEFT_PAD           = 8    # px — text indent after strip
    RIGHT_PAD          = 14   # px — room for scroll bar
    SCROLL_BAR_WIDTH   = 4    # px
    SCROLL_BAR_COLOR   = ( 70,  70,  80)
    SCROLL_THUMB_COLOR = (140, 140, 160)
    BG_COLOR           = (  8,   8,  12)
    BORDER_COLOR       = ( 45,  45,  55)

    def __init__(self, x, y, width, height, font=None):
        self.rect = Rect(x, y, width, height)
        self.messages: list[tuple[str, tuple, str]] = []  # (text, color, category)
        self.scroll_offset = 0
        self.current_input = ""
        self.input_height  = 22
        self.show_input_area = False
        self.compact = False   # Toggle with Tab

        self._build_fonts()
        self._recalc_max_lines()

    # ------------------------------------------------------------------
    # Font / layout helpers
    # ------------------------------------------------------------------

    def _build_fonts(self):
        size = self.COMPACT_FONT_SIZE if self.compact else self.EXPANDED_FONT_SIZE
        try:
            self.font = pygame.font.SysFont("consolas", size)
        except Exception:
            self.font = pygame.font.Font(None, size + 2)
        self.line_height = self.font.get_linesize() + (0 if self.compact else 2)

    def _recalc_max_lines(self):
        usable = self.rect.height - (self.input_height if self.show_input_area else 0)
        self.max_lines = max(1, usable // self.line_height)

    def toggle_compact(self):
        """Call this when the player presses Tab (or whatever key you assign)."""
        self.compact = not self.compact
        self._build_fonts()
        self._recalc_max_lines()
        self.clamp_scroll_offset()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_message(self, text: str, color=None):
        if color is None:
            color = (220, 220, 220)

        category = _detect_category(text, color)

        # Word-wrap against usable width
        max_w = self.rect.width - self.LEFT_STRIP_WIDTH - self.LEFT_PAD - self.RIGHT_PAD - 4
        words = text.split(" ")
        lines, current = [], []
        for word in words:
            test = " ".join(current + [word])
            if self.font.size(test)[0] <= max_w:
                current.append(word)
            else:
                if current:
                    lines.append(" ".join(current))
                current = [word]
        if current:
            lines.append(" ".join(current))

        for line in lines:
            self.messages.append((line, color, category))

        # Auto-scroll to bottom on new message
        self.scroll_offset = 0
        self._recalc_max_lines()
        self.clamp_scroll_offset()

    def truncate_messages(self, max_messages: int):
        if len(self.messages) > max_messages:
            self.messages = self.messages[-max_messages:]
            self.scroll_offset = 0
            self.clamp_scroll_offset()

    def clear_last_input(self):
        self.current_input = ""

    def scroll_up(self):
        self.scroll_offset += 1
        self.clamp_scroll_offset()

    def scroll_down(self):
        self.scroll_offset -= 1
        self.clamp_scroll_offset()

    def clamp_scroll_offset(self):
        max_offset = max(0, len(self.messages) - self.max_lines)
        self.scroll_offset = max(0, min(self.scroll_offset, max_offset))

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def render(self, surface: pygame.Surface):
        self._recalc_max_lines()

        # --- Transparent background — no fill, tiles show through ---
        # (nothing drawn here; the game area renders beneath this rect)



        # --- Visible message slice ---
        start = max(0, len(self.messages) - self.max_lines - self.scroll_offset)
        end   = start + self.max_lines
        visible = self.messages[start:end]
        total_visible = len(visible)

        # Scrolled-back indicator label
        is_scrolled = self.scroll_offset > 0

        y = self.rect.y + 2
        text_x = self.rect.x + self.LEFT_STRIP_WIDTH + self.LEFT_PAD

        for i, (text, color, category) in enumerate(visible):
            strip_color, color_override = _CATEGORY_STYLE.get(category, _CATEGORY_STYLE["default"])

            # Fade older messages
            age = total_visible - 1 - i          # 0 = oldest visible
            recency = total_visible - 1 - age    # 0 = oldest, total_visible-1 = newest
            if recency >= _FADE_RECENT_COUNT:
                alpha = 255
            else:
                # Linear fade from _FADE_MIN_ALPHA to 255
                t = recency / max(_FADE_RECENT_COUNT - 1, 1)
                alpha = int(_FADE_MIN_ALPHA + (_255 := 255 - _FADE_MIN_ALPHA) * t)

            # Draw category strip
            strip_rect = pygame.Rect(
                self.rect.x, y,
                self.LEFT_STRIP_WIDTH, self.line_height - 1
            )
            strip_surf = pygame.Surface((strip_rect.width, strip_rect.height), pygame.SRCALPHA)
            sr, sg, sb = strip_color
            strip_surf.fill((sr, sg, sb, alpha))
            surface.blit(strip_surf, strip_rect.topleft)

            # Draw text
            draw_color = color_override if color_override else color
            try:
                text_surf = self.font.render(text, True, draw_color)
            except Exception:
                text_surf = self.font.render("", True, draw_color)

            # Apply alpha via a temp surface
            tmp = pygame.Surface(text_surf.get_size(), pygame.SRCALPHA)
            tmp.blit(text_surf, (0, 0))
            tmp.set_alpha(alpha)
            surface.blit(tmp, (text_x, y))

            y += self.line_height

        # --- Scroll indicator (right edge) ---
        self._draw_scroll_bar(surface)

        # --- Scrolled-back banner ---
        if is_scrolled:
            self._draw_scroll_banner(surface)

        # --- Input area ---
        if self.show_input_area:
            self._draw_input_area(surface)

    def _draw_scroll_bar(self, surface: pygame.Surface):
        total = len(self.messages)
        if total <= self.max_lines:
            return  # No scrollbar needed

        bar_x      = self.rect.right - self.SCROLL_BAR_WIDTH - 2
        bar_top    = self.rect.top + 2
        bar_height = self.rect.height - 4
        if self.show_input_area:
            bar_height -= self.input_height

        # Track
        pygame.draw.rect(
            surface, self.SCROLL_BAR_COLOR,
            (bar_x, bar_top, self.SCROLL_BAR_WIDTH, bar_height)
        )

        # Thumb — represents max_lines / total proportion
        thumb_ratio  = min(1.0, self.max_lines / total)
        thumb_height = max(8, int(bar_height * thumb_ratio))

        # Position: scroll_offset=0 → thumb at bottom, max_offset → thumb at top
        max_offset   = max(1, total - self.max_lines)
        scroll_ratio = self.scroll_offset / max_offset           # 0=bottom, 1=top
        thumb_y      = bar_top + int((bar_height - thumb_height) * (1.0 - scroll_ratio))

        pygame.draw.rect(
            surface, self.SCROLL_THUMB_COLOR,
            (bar_x, thumb_y, self.SCROLL_BAR_WIDTH, thumb_height),
            border_radius=2
        )

    def _draw_scroll_banner(self, surface: pygame.Surface):
        """Small subtle label showing we're scrolled back."""
        label = f"  ↑ scrolled back ({self.scroll_offset})  "
        try:
            s = self.font.render(label, True, (120, 120, 140))
        except Exception:
            return
        bx = self.rect.right - s.get_width() - self.SCROLL_BAR_WIDTH - 6
        by = self.rect.top + 3
        bg = pygame.Surface((s.get_width() + 4, s.get_height()), pygame.SRCALPHA)
        bg.fill((20, 20, 30, 180))
        surface.blit(bg, (bx - 2, by))
        surface.blit(s, (bx, by))

    def _draw_input_area(self, surface: pygame.Surface):
        iy = self.rect.bottom - self.input_height
        pygame.draw.rect(
            surface, (18, 18, 24),
            (self.rect.x, iy, self.rect.width, self.input_height)
        )
        pygame.draw.line(
            surface, self.BORDER_COLOR,
            (self.rect.x, iy), (self.rect.right, iy), 1
        )
        prompt = "> " + self.current_input
        try:
            ps = self.font.render(prompt, True, (200, 220, 255))
        except Exception:
            ps = self.font.render("> ", True, (200, 220, 255))
        surface.blit(ps, (self.rect.x + self.LEFT_PAD, iy + 4))