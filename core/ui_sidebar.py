import pygame
import config


# ── Palette ────────────────────────────────────────────────────────────────
_BG          = (10,  8,  10)     # near-black with warm tint
_BG_SECTION  = (18, 14,  18)     # aged stone
_BORDER      = (52, 42,  46)     # worn iron / dark bronze

_ACCENT      = (96, 38,  38)     # dried blood crimson

_TEXT_DIM    = (112, 102,  96)   # dusty parchment
_TEXT_NORMAL = (188, 178, 168)   # aged bone
_TEXT_BRIGHT = (232, 224, 210)   # candlelit ivory

_GOLD        = (164, 124,  52)   # tarnished gold
_CYAN        = ( 72, 132, 136)   # muted spectral cyan
_ORANGE      = (176,  96,  42)   # ember orange

_RED_LO      = (148,  42,  42)   # dark blood red
_YEL_MID     = (168, 148,  54)   # old brass
_GRN_HI      = ( 72, 132,  78)   # swamp/alchemy green


# ── Tiny helpers ────────────────────────────────────────────────────────────

def _font(size: int, bold: bool = False) -> pygame.font.Font:
    try:
        return pygame.font.SysFont("consolas", size, bold=bold)
    except Exception:
        return pygame.font.Font(None, size + 2)


def _txt(surface, font, text, color, x, y):
    surface.blit(font.render(text, True, color), (x, y))


def _txt_centered(surface, font, text, color, cx, y):
    s = font.render(text, True, color)
    surface.blit(s, (cx - s.get_width() // 2, y))


def _section_header(surface, font, label: str, x: int, y: int, width: int) -> int:
    """Draws a section label with a left accent bar. Returns new y."""
    bar_h = font.get_linesize()
    # left accent bar
    pygame.draw.rect(surface, _ACCENT, (x, y + 2, 3, bar_h - 2))
    _txt(surface, font, label, _TEXT_BRIGHT, x + 8, y)
    # full-width underline
    pygame.draw.line(surface, _BORDER, (x, y + bar_h + 2), (x + width, y + bar_h + 2), 1)
    return y + bar_h + 7


def _fill_bar(surface, x: int, y: int, w: int, h: int,
              value: float, max_value: float,
              filled_color, empty_color=(30, 30, 38),
              text: str = "", font=None, border_radius: int = 3):
    """Draws a filled bar.  text is drawn centered over it if provided."""
    pct = max(0.0, min(1.0, value / max_value)) if max_value > 0 else 0.0
    # background
    pygame.draw.rect(surface, empty_color,  (x, y, w, h), border_radius=border_radius)
    # fill
    fill_w = max(0, int(w * pct))
    if fill_w > 0:
        pygame.draw.rect(surface, filled_color, (x, y, fill_w, h), border_radius=border_radius)
    # border
    pygame.draw.rect(surface, _BORDER, (x, y, w, h), 1, border_radius=border_radius)
    # label
    if text and font:
        ts = font.render(text, True, _TEXT_BRIGHT)
        surface.blit(ts, (x + w // 2 - ts.get_width() // 2,
                          y + h // 2 - ts.get_height() // 2))


def _xp_bar(surface, x: int, y: int, w: int,
            current_xp: int, xp_needed: int, font):
    bar_h = 5
    pct = current_xp / xp_needed if xp_needed > 0 else 0.0
    pygame.draw.rect(surface, (30, 30, 38), (x, y, w, bar_h), border_radius=2)
    fill_w = int(w * pct)
    if fill_w > 0:
        pygame.draw.rect(surface, _CYAN, (x, y, fill_w, bar_h), border_radius=2)
    _txt(surface, font,
         f"XP  {current_xp}/{xp_needed}",
         _TEXT_DIM, x, y + bar_h + 3)
    return y + bar_h + font.get_linesize() + 5


def _quick_slot(surface, font_key, font_label,
                x: int, y: int, w: int, h: int,
                key_label: str, item):
    """Draw one Quick Bar slot box."""
    filled = item is not None
    bg     = (22, 22, 30) if not filled else (24, 30, 38)
    border = _BORDER if not filled else _ACCENT
    pygame.draw.rect(surface, bg,     (x, y, w, h), border_radius=4)
    pygame.draw.rect(surface, border, (x, y, w, h), 1, border_radius=4)

    # key badge top-left
    badge_s = font_key.render(f"[{key_label.upper()}]", True,
                              _CYAN if filled else _TEXT_DIM)
    surface.blit(badge_s, (x + 4, y + 3))

    # item name or empty placeholder
    if filled:
        name = item.name if len(item.name) <= 14 else item.name[:13] + "…"
        ns = font_label.render(name, True, item.color)
    else:
        ns = font_label.render("— empty —", True, _TEXT_DIM)
    surface.blit(ns, (x + 4, y + h - font_label.get_linesize() - 4))


def _ability_row(surface, font_key, font_label,
                 x: int, y: int, w: int,
                 index: int, ability) -> int:
    """Draw one ability row. Returns new y."""
    h = font_label.get_linesize() + 8
    ready = ability.current_cooldown == 0

    bg = (20, 28, 30) if ready else (28, 22, 16)
    pygame.draw.rect(surface, bg, (x, y, w, h), border_radius=3)
    pygame.draw.rect(surface, _BORDER, (x, y, w, h), 1, border_radius=3)

    # hotkey badge
    badge_color = _CYAN if ready else _ORANGE
    badge_text  = str(index + 1)
    bs = font_key.render(badge_text, True, badge_color)
    bw = bs.get_width() + 8
    pygame.draw.rect(surface, (30, 30, 40), (x, y, bw, h), border_radius=3)
    surface.blit(bs, (x + 4, y + h // 2 - bs.get_height() // 2))

    # ability name
    name_color = _TEXT_BRIGHT if ready else _TEXT_DIM
    name = ability.name if len(ability.name) <= 16 else ability.name[:15] + "…"
    ns = font_label.render(name, True, name_color)
    surface.blit(ns, (x + bw + 6, y + h // 2 - ns.get_height() // 2))

    # cooldown pip
    if not ready:
        cd_s = font_key.render(f"CD:{ability.current_cooldown}", True, _ORANGE)
        surface.blit(cd_s, (x + w - cd_s.get_width() - 4,
                            y + h // 2 - cd_s.get_height() // 2))

    return y + h + 3


def _effect_tag(surface, font, x: int, y: int, name: str, turns: int) -> int:
    """Draw a pill tag for one status effect. Returns right edge x."""
    label  = f"{name}  {turns}"
    ls     = font.render(label, True, _TEXT_BRIGHT)
    pw, ph = ls.get_width() + 10, ls.get_height() + 4
    pygame.draw.rect(surface, (35, 25, 15), (x, y, pw, ph), border_radius=ph // 2)
    pygame.draw.rect(surface, _ORANGE,      (x, y, pw, ph), 1, border_radius=ph // 2)
    surface.blit(ls, (x + 5, y + 2))
    return x + pw + 5   # next tag x


# ── Main entry point ────────────────────────────────────────────────────────

def draw_sidebar(game) -> None:
    """
    Call this instead of (or from within) Game.draw_ui().
    `game` is the Game instance — needs: screen, player, game_state,
    current_level, get_current_entity(), check_stairs_interaction(),
    check_npc_interaction(), check_dungeon_npc_interaction().
    """
    screen = game.screen
    p      = game.player

    PAD   = 10                               # inner horizontal padding
    x0    = config.GAME_AREA_WIDTH + PAD     # left edge of text content
    x1    = config.SCREEN_WIDTH - PAD        # right edge
    W     = x1 - x0                          # usable content width
    cx    = config.GAME_AREA_WIDTH + config_panel_w(game) // 2  # center x

    # ── Panel background ──────────────────────────────────────────────
    panel_rect = pygame.Rect(config.GAME_AREA_WIDTH, 0,
                             config_panel_w(game), config.SCREEN_HEIGHT)
    pygame.draw.rect(screen, _BG, panel_rect)
    # left border line
    pygame.draw.line(screen, _BORDER,
                     (config.GAME_AREA_WIDTH, 0),
                     (config.GAME_AREA_WIDTH, config.SCREEN_HEIGHT), 1)

    # ── Fonts (built fresh; cheap because SysFont caches) ─────────────
    fH  = _font(16, bold=True)   # section header
    fN  = _font(14)              # normal info
    fSm = _font(12)              # small / dim
    fKy = _font(13, bold=True)   # key badges

    y = 10

    # ════════════════════════════════════════════════════════════════════
    # 1.  PLAYER IDENTITY
    # ════════════════════════════════════════════════════════════════════
    y = _section_header(screen, fH, "PLAYER", x0, y, W)

    # Name + class on one line, level right-aligned
    name_str  = p.name
    class_str = getattr(p, "class_name", "")
    lvl_str   = f"Lv {p.level}"
    _txt(screen, fN, f"{name_str}  ·  {class_str}", _TEXT_NORMAL, x0, y)
    lv_s = fN.render(lvl_str, True, _CYAN)
    screen.blit(lv_s, (x1 - lv_s.get_width(), y))
    y += fN.get_linesize() + 4

    # XP bar
    y = _xp_bar(screen, x0, y, W, p.current_xp, p.xp_to_next_level, fSm)

    # Gold
    g_s = fN.render(f"◆ {p.gold} gp", True, _GOLD)
    screen.blit(g_s, (x0, y))
    y += fN.get_linesize() + 12

    # ════════════════════════════════════════════════════════════════════
    # 2.  VITALS  (HP + Hunger as bars)
    # ════════════════════════════════════════════════════════════════════
    y = _section_header(screen, fH, "VITALS", x0, y, W)

    bar_h = 16

    # HP color by threshold
    hp_pct = p.hp / p.max_hp if p.max_hp > 0 else 0
    hp_col = _RED_LO if hp_pct < 0.33 else _YEL_MID if hp_pct < 0.66 else _GRN_HI

    _fill_bar(screen, x0, y, W, bar_h,
              p.hp, p.max_hp, hp_col,
              text=f"HP  {p.hp} / {p.max_hp}", font=fSm)
    y += bar_h + 5

    # Hunger color by threshold
    hun = getattr(p, "hunger", 100)
    hun_col = _RED_LO if hun < 20 else _YEL_MID if hun < 50 else _GRN_HI
    _fill_bar(screen, x0, y, W, bar_h,
              hun, 100, hun_col,
              text=f"Hunger  {hun} / 100", font=fSm)
    y += bar_h + 12

    # ════════════════════════════════════════════════════════════════════
    # 3.  QUICK BAR
    # ════════════════════════════════════════════════════════════════════
    y = _section_header(screen, fH, "QUICK BAR", x0, y, W)

    slot_w = (W - 4) // 2
    slot_h = 36
    _quick_slot(screen, fKy, fSm, x0,           y, slot_w, slot_h,
                "q", p.quick_bar.get("q"))
    _quick_slot(screen, fKy, fSm, x0 + slot_w + 4, y, slot_w, slot_h,
                "f", p.quick_bar.get("f"))
    y += slot_h + 12

    # ════════════════════════════════════════════════════════════════════
    # 4.  ABILITIES
    # ════════════════════════════════════════════════════════════════════
    y = _section_header(screen, fH, "ABILITIES", x0, y, W)

    abilities = list(p.abilities.values()) if p.abilities else []
    if not abilities:
        _txt(screen, fSm, "none", _TEXT_DIM, x0, y)
        y += fSm.get_linesize() + 5
    else:
        for i, ab in enumerate(abilities):
            y = _ability_row(screen, fKy, fN, x0, y, W, i, ab)
    y += 8

    # ════════════════════════════════════════════════════════════════════
    # 5.  EFFECTS
    # ════════════════════════════════════════════════════════════════════
    y = _section_header(screen, fH, "EFFECTS", x0, y, W)

    effects = getattr(p, "active_status_effects", [])
    if not effects:
        _txt(screen, fSm, "none", _TEXT_DIM, x0, y)
        y += fSm.get_linesize() + 5
    else:
        tag_x  = x0
        row_h  = fSm.get_linesize() + 6
        for eff in effects:
            turns = getattr(eff, "turns_left", "?")
            label = eff.name
            ls    = fSm.render(f"{label}  {turns}", True, _TEXT_BRIGHT)
            pw    = ls.get_width() + 10
            if tag_x + pw > x1:
                tag_x  = x0
                y     += row_h + 3
            tag_x = _effect_tag(screen, fSm, tag_x, y, label, turns)
        y += row_h + 10

    # ════════════════════════════════════════════════════════════════════
    # 6.  STATUS  (location / turn)
    # ════════════════════════════════════════════════════════════════════
    y = _section_header(screen, fH, "STATUS", x0, y, W)

    if game.game_state == "tavern":
        _txt(screen, fSm, "The Prancing Pony", _CYAN, x0, y)
        y += fSm.get_linesize() + 3
    else:
        _txt(screen, fSm, f"Depth  B{game.current_level}F", _CYAN, x0, y)
        y += fSm.get_linesize() + 3
        current_ent = game.get_current_entity()
        if current_ent:
            turn_color = _GRN_HI if current_ent == p else _RED_LO
            turn_label = "Your turn" if current_ent == p else f"{current_ent.name}'s turn"
            _txt(screen, fSm, turn_label, turn_color, x0, y)
            y += fSm.get_linesize() + 3
    y += 10

    # ════════════════════════════════════════════════════════════════════
    # 7.  CONTROLS  (context-sensitive, bottom of panel, dim)
    # ════════════════════════════════════════════════════════════════════
    controls = _build_controls(game)
    # draw from bottom up so they don't overlap sections above
    bottom_y = config.SCREEN_HEIGHT - 8
    for ctrl in reversed(controls):
        cs = fSm.render(ctrl, True, _TEXT_DIM)
        bottom_y -= cs.get_height() + 2
        if bottom_y < y:
            break
        screen.blit(cs, (x0, bottom_y))


# ── Helpers used by draw_sidebar ────────────────────────────────────────────

def config_panel_w(game) -> int:
    return config.UI_PANEL_WIDTH


def _build_controls(game) -> list[str]:
    
    gs = game.game_state
    controls = []
    if gs == "tavern":
        if game.check_tavern_door_interaction():
            controls.append("+ → enter dungeon")
        npc = game.check_npc_interaction()
        if npc:
            controls.append(f"F → talk to {npc.name}")
        controls += ["arrows/WASD  move", "I  inventory", "C  character"]
    elif gs == "dungeon":
        sd = game.check_stairs_interaction()
        if sd:
            controls.append(f"{'<' if sd == 'up' else '>'}  {'ascend' if sd == 'up' else 'descend'}")
        npc = game.check_dungeon_npc_interaction()
        if npc:
            controls.append(f"F → {npc.name}")
        else:
            controls.append("SPACE  attack / pick up")
        controls += ["arrows/WASD  move", "1-9  abilities",
                     "I  inventory", "C  character", "Q/F  quick bar"]
    elif gs == "inventory":
        controls += ["I  close", "↑↓  navigate", "Enter  select"]
    elif gs == "inventory_menu":
        controls += ["U  use", "E  equip", "D  drop", "C  cancel"]
    elif gs == "character_menu":
        controls += ["C  close", "I  inventory"]
    elif gs == "trade":
        controls += ["buy <item>", "sell <item>"]
    elif gs == "targeting":
        controls += ["arrows  move cursor", "Enter  confirm", "Esc  cancel"]
    return controls