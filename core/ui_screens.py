import pygame
import graphics
import config
from items.items import CampfireKit, Weapon, Armor, OffHand, Potion, Food, Accessory, Tools, Junk

# ── Palette ──────────────────────────────────────────────────────────────────

_BG          = (10,   8,  10)   # abyss black
_BG_PANEL    = (18,  14,  18)   # obsidian stone

_BG_SLOT     = (24,  18,  22)   # worn granite
_BG_SLOT_ALT = (30,  22,  28)   # deeper stone variation

_BG_SELECTED = (52,  32,  36)   # blood-tinted selection

_BORDER      = (50,  40,  44)   # dark iron
_BORDER_LT   = (78,  64,  68)   # aged steel edge

_ACCENT      = (96,  38,  38)   # dried blood crimson
_ACCENT_GOLD = (118,  88,  34)  # tarnished brass

_GLOW_SEL    = (140,  62,  62)  # crimson glow
_GLOW_EQ     = (176, 132,  52)  # relic gold glow

_TEXT_DIM    = (112, 102,  96)  # dusty parchment
_TEXT_NORMAL = (188, 178, 168)  # aged bone
_TEXT_BRIGHT = (232, 224, 210)  # candlelit ivory

_GOLD        = (164, 124,  52)  # old relic gold
_CYAN        = (72, 132, 136)   # spectral teal
_GREEN       = (74, 122,  76)   # swamp herb green

_RED         = (148,  42,  42)  # coagulated blood
_ORANGE      = (176,  96,  42)  # ember orange

_PURPLE      = (92,  62, 116)   # abyss purple
_WHITE       = (214, 206, 194)  # aged ivory

SLOT_SIZE    = 87   # px — each inventory cell
SLOT_GAP     = 4    # px — gap between cells
SPRITE_PAD   = 6    # px — padding inside each cell around the sprite
COLS         = 5    # inventory grid columns


# ── Font helpers ──────────────────────────────────────────────────────────────
def _f(size, bold=False):
    try:    return pygame.font.SysFont("consolas", size, bold=bold)
    except: return pygame.font.Font(None, size + 2)

def _blit(surf, font, text, color, x, y):
    surf.blit(font.render(str(text), True, color), (x, y))

def _blit_center(surf, font, text, color, cx, y):
    s = font.render(str(text), True, color)
    surf.blit(s, (cx - s.get_width() // 2, y))

def _wrap(font, text, max_w):
    words = str(text).split()
    lines, cur = [], []
    for w in words:
        test = " ".join(cur + [w])
        if font.size(test)[0] <= max_w:
            cur.append(w)
        else:
            if cur: lines.append(" ".join(cur))
            cur = [w]
    if cur: lines.append(" ".join(cur))
    return lines or [""]

def _blit_wrap(surf, font, text, color, x, y, max_w):
    for line in _wrap(font, text, max_w):
        surf.blit(font.render(line, True, color), (x, y))
        y += font.get_linesize() + 2
    return y

def _section_label(surf, font, label, x, y, w):
    h = font.get_linesize()
    pygame.draw.rect(surf, _ACCENT, (x, y + 2, 3, h - 2))
    _blit(surf, font, label, _TEXT_BRIGHT, x + 8, y)
    pygame.draw.line(surf, _BORDER, (x, y + h + 3), (x + w, y + h + 3), 1)
    return y + h + 9

def _save_row(surf, font, label, bonus, proficient, x, y, w):
    dot_color = _GREEN if proficient else _TEXT_DIM
    pygame.draw.circle(surf, dot_color, (x + 5, y + font.get_linesize() // 2), 4)
    _blit(surf, font, label, _TEXT_NORMAL, x + 14, y)
    mod_str = f"+{bonus}" if bonus >= 0 else str(bonus)
    bs = font.render(mod_str, True, _GREEN if proficient else _TEXT_DIM)
    surf.blit(bs, (x + w - bs.get_width(), y))
    return y + font.get_linesize() + 3

def _stat_box(surf, font_big, font_small, label, score, modifier, x, y, size=52):
    pygame.draw.rect(surf, _BG_PANEL, (x, y, size, size), border_radius=4)
    pygame.draw.rect(surf, _BORDER_LT, (x, y, size, size), 1, border_radius=4)
    circ_r  = 11
    circ_cx = x + size // 2
    circ_cy = y + size - circ_r - 2
    pygame.draw.circle(surf, _BG, (circ_cx, circ_cy), circ_r)
    pygame.draw.circle(surf, _BORDER_LT, (circ_cx, circ_cy), circ_r, 1)
    mod_str = f"+{modifier}" if modifier >= 0 else str(modifier)
    ms = font_small.render(mod_str, True, _TEXT_BRIGHT)
    surf.blit(ms, (circ_cx - ms.get_width() // 2, circ_cy - ms.get_height() // 2))
    ss = font_big.render(str(score), True, _TEXT_BRIGHT)
    surf.blit(ss, (circ_cx - ss.get_width() // 2, y + 8))
    ls = font_small.render(label, True, _TEXT_DIM)
    surf.blit(ls, (circ_cx - ls.get_width() // 2, y + size + 2))


# ── Sprite helper ─────────────────────────────────────────────────────────────
def _get_sprite(char, size):
    """Return a pygame Surface with the tile sprite scaled to `size`×`size`."""
    try:
        base = graphics.get_tile_surface(char)
        if base is None:
            raise ValueError
        if base.get_width() != size:
            return pygame.transform.scale(base, (size, size))
        return base
    except Exception:
        s = pygame.Surface((size, size), pygame.SRCALPHA)
        s.fill((40, 40, 55))
        return s


# ── Item-type label ───────────────────────────────────────────────────────────
def _item_type_label(item):
    if isinstance(item, Weapon):   return "Weapon"
    if isinstance(item, Armor):    return "Armor"
    if isinstance(item, OffHand):  return "Off-hand"
    if isinstance(item, Potion):   return "Potion"
    if isinstance(item, Food):     return "Food"
    if isinstance(item, Accessory):return "Accessory"
    if isinstance(item, Tools):    return "Tool"
    if isinstance(item, CampfireKit): return "Tool"
    if isinstance(item, Junk):     return "Junk"
    return type(item).__name__

def _item_type_color(item):
    if isinstance(item, Weapon):   return (180, 80, 80)
    if isinstance(item, Armor):    return _CYAN
    if isinstance(item, OffHand):  return (180, 140, 80)
    if isinstance(item, Potion):   return (160, 80, 200)
    if isinstance(item, Food):     return _GREEN
    if isinstance(item, Accessory):return _GOLD
    if isinstance(item, Tools):    return _ORANGE
    return _TEXT_DIM

def _item_stats(item):
    """Return list of (label, value) stat rows for the detail card."""
    rows = []
    if isinstance(item, Weapon):
        rows += [("Damage", item.damage_dice),
                 ("Dmg Mod", f"+{item.damage_modifier}"),
                 ("Atk Bonus", f"+{item.attack_bonus}"),
                 ("Spell Bonus", f"+{item.spell_bonus}"),
                 ("Two-Handed", "Yes" if item.is_two_handed else "No")]
    elif isinstance(item, Armor):
        rows += [("AC Bonus", f"+{item.ac_bonus}"),
                 ("Category", item.category or "—")]
    elif isinstance(item, OffHand):
        if item.ac_bonus:
            rows.append(("Defense", f"+{item.ac_bonus}"))
        if item.damage_dice:
            rows += [("Damage", item.damage_dice),
                     ("Dmg Mod", f"+{item.damage_modifier}"),
                     ("Atk Bonus", f"+{item.attack_bonus}"),
                     ("Spell Bonus", f"+{item.spell_bonus}")]
    elif isinstance(item, Potion):
        rows += [("Effect", item.effect_type),
                 ("Value", item.effect_value)]
    elif isinstance(item, Food):
        rows += [("Hunger", f"+{item.healing_value}")]
    if hasattr(item, "price") and item.price:
        rows.append(("Price", f"{item.price} gp"))
    return rows


# ── Draw one inventory slot cell ──────────────────────────────────────────────
def _draw_slot(surf, item, x, y, selected=False, size=SLOT_SIZE):
    sprite_size = size - SPRITE_PAD * 2

    # background
    bg = _BG_SELECTED if selected else _BG_SLOT
    pygame.draw.rect(surf, bg, (x, y, size, size), border_radius=5)

    # border / glow
    if selected:
        pygame.draw.rect(surf, _GLOW_SEL, (x, y, size, size), 2, border_radius=5)
        # outer glow ring
        glow = pygame.Surface((size + 6, size + 6), pygame.SRCALPHA)
        pygame.draw.rect(glow, (*_GLOW_SEL, 60), (0, 0, size + 6, size + 6), 3, border_radius=7)
        surf.blit(glow, (x - 3, y - 3))
    else:
        pygame.draw.rect(surf, _BORDER, (x, y, size, size), 1, border_radius=5)

    if item is None:
        # empty: dashed cross lines
        cx, cy = x + size // 2, y + size // 2
        pygame.draw.line(surf, _BORDER_LT, (cx - 6, cy), (cx + 6, cy), 1)
        pygame.draw.line(surf, _BORDER_LT, (cx, cy - 6), (cx, cy + 6), 1)
        return

    # sprite
    sprite = _get_sprite(item.char, sprite_size)
    surf.blit(sprite, (x + SPRITE_PAD, y + SPRITE_PAD))

    # rarity corner dot — just use item color
    pygame.draw.circle(surf, item.color, (x + size - 5, y + 5), 3)


# ── Draw an equipment slot (labeled, fixed position) ─────────────────────────
def _draw_equip_slot(surf, item, label, x, y, size=SLOT_SIZE, font_label=None):
    fSm = font_label or _f(10)
    sprite_size = size - SPRITE_PAD * 2

    # slot box
    eq = item is not None
    bg = (18, 24, 32) if eq else _BG_SLOT
    bc = _GLOW_EQ if eq else _BORDER
    pygame.draw.rect(surf, bg, (x, y, size, size), border_radius=5)
    pygame.draw.rect(surf, bc, (x, y, size, size), 1 if not eq else 2, border_radius=5)

    if item:
        sprite = _get_sprite(item.char, sprite_size)
        surf.blit(sprite, (x + SPRITE_PAD, y + SPRITE_PAD))
        # gold glow
        glow = pygame.Surface((size + 4, size + 4), pygame.SRCALPHA)
        pygame.draw.rect(glow, (*_GLOW_EQ, 50), (0, 0, size + 4, size + 4), 2, border_radius=6)
        surf.blit(glow, (x - 2, y - 2))
    else:
        cx, cy = x + size // 2, y + size // 2
        pygame.draw.line(surf, _BORDER_LT, (cx - 8, cy), (cx + 8, cy), 1)
        pygame.draw.line(surf, _BORDER_LT, (cx, cy - 8), (cx, cy + 8), 1)

    # label below
    ls = fSm.render(label, True, _GOLD if eq else _TEXT_DIM)
    surf.blit(ls, (x + size // 2 - ls.get_width() // 2, y + size + 2))


# ── Detail card (right column) ────────────────────────────────────────────────
def _draw_detail_card(surf, item, x, y, w, h):
    fSec  = _f(16, bold=True)
    fInfo = _f(14)
    fSm   = _f(12)
    fBig  = _f(14, bold=True)

    pygame.draw.rect(surf, _BG_PANEL, (x, y, w, h), border_radius=6)
    pygame.draw.rect(surf, _BORDER_LT, (x, y, w, h), 1, border_radius=6)

    pad = 10
    cx  = x + w // 2
    iy  = y + pad

    if item is None:
        msg = _f(12).render("Select an item", True, _TEXT_DIM)
        surf.blit(msg, (cx - msg.get_width() // 2, y + h // 2 - msg.get_height() // 2))
        return

    # large sprite
    SPRITE_BIG = min(72, w - pad * 2)
    sprite = _get_sprite(item.char, SPRITE_BIG)
    # tint with item color
    tinted = sprite.copy()
    surf.blit(tinted, (cx - SPRITE_BIG // 2, iy))
    iy += SPRITE_BIG + 8

    # type badge
    type_label = _item_type_label(item)
    type_color = _item_type_color(item)
    tl = fSm.render(type_label, True, type_color)
    tw = tl.get_width() + 12
    pygame.draw.rect(surf, (*type_color, 30), (cx - tw // 2, iy, tw, tl.get_height() + 4), border_radius=3)
    pygame.draw.rect(surf, type_color,        (cx - tw // 2, iy, tw, tl.get_height() + 4), 1, border_radius=3)
    surf.blit(tl, (cx - tl.get_width() // 2, iy + 2))
    iy += tl.get_height() + 10

    # item name
    nl = fBig.render(item.name, True, item.color)
    if nl.get_width() > w - pad * 2:
        iy = _blit_wrap(surf, fSec, item.name, item.color, x + pad, iy, w - pad * 2)
    else:
        surf.blit(nl, (cx - nl.get_width() // 2, iy))
        iy += nl.get_height() + 4

    # divider
    pygame.draw.line(surf, _BORDER, (x + pad, iy), (x + w - pad, iy), 1)
    iy += 8

    # stats
    stats = _item_stats(item)
    for label, val in stats:
        _blit(surf, fSm, label, _TEXT_DIM, x + pad, iy)
        vs = fInfo.render(str(val), True, _CYAN)
        surf.blit(vs, (x + w - vs.get_width() - pad, iy))
        iy += fInfo.get_linesize() + 4

    if stats:
        pygame.draw.line(surf, _BORDER, (x + pad, iy), (x + w - pad, iy), 1)
        iy += 8

    # description
    if hasattr(item, "description") and item.description:
        _blit_wrap(surf, fSm, item.description, _TEXT_DIM, x + pad, iy, w - pad * 2)


# ═══════════════════════════════════════════════════════════════════════════════
# INVENTORY SCREEN
# ═══════════════════════════════════════════════════════════════════════════════
def render_inventory_screen(game):
    surf = game.inventory_ui_surface
    surf.fill((0, 0, 0, 0))
    player  = game.player
    SW = surf.get_width()
    SH = surf.get_height()

    PAD  = 12
    fHdr = _f(18, bold=True)
    fSec = _f(16, bold=True)
    fSm  = _f(14)
    fXs  = _f(12)

    # ── Column layout ────────────────────────────────────────────────────
    # Left: item grid  |  Center: paper-doll  |  Right: detail card
    DETAIL_W = max(160, int(SW * 0.24))
    DOLL_W   = max(180, int(SW * 0.28))
    GRID_W   = SW - DOLL_W - DETAIL_W - PAD * 4

    grid_x   = PAD
    doll_x   = grid_x + GRID_W + PAD
    detail_x = doll_x + DOLL_W + PAD

    # Reset slot rect dicts so mouse handler can detect clicks each frame
    game._equip_slot_rects = {}
    game._inventory_slot_rects = {}

    # panel backgrounds
    for px2, pw in ((grid_x, GRID_W), (doll_x, DOLL_W), (detail_x, DETAIL_W)):
        r = pygame.Rect(px2, PAD, pw, SH - PAD * 2)
        pygame.draw.rect(surf, _BG_PANEL, r, border_radius=6)
        pygame.draw.rect(surf, _BORDER,   r, 1, border_radius=6)

    # ── LEFT: inventory grid ─────────────────────────────────────────────
    y = PAD + 10
    _blit(surf, fHdr, "INVENTORY", _TEXT_BRIGHT, grid_x + 8, y)
    cap_s = fSm.render(f"{len(player.inventory.items)}/{player.inventory.capacity}", True, _GOLD)
    surf.blit(cap_s, (grid_x + GRID_W - cap_s.get_width() - 8, y + 2))
    y += fHdr.get_linesize() + 6
    pygame.draw.line(surf, _BORDER, (grid_x + 6, y), (grid_x + GRID_W - 6, y), 1)
    y += 8

    items    = player.inventory.items
    sel_idx  = game.selected_inventory_index
    sel_item = items[sel_idx] if 0 <= sel_idx < len(items) else None

    # grid cells
    grid_inner_w = GRID_W - PAD * 2
    cell = SLOT_SIZE + SLOT_GAP
    cols = max(1, grid_inner_w // cell)
    gx0  = grid_x + PAD

    for i in range(player.inventory.capacity):
        item = items[i] if i < len(items) else None
        col  = i % cols
        row  = i // cols
        cx   = gx0 + col * cell
        cy   = y   + row * cell
        _draw_slot(surf, item, cx, cy, selected=(i == sel_idx))
        game._inventory_slot_rects[i] = pygame.Rect(cx, cy, SLOT_SIZE, SLOT_SIZE)

        # slot number (bottom-right corner)
        badge = fXs.render(str((i + 1) % 10), True, _TEXT_DIM)
        surf.blit(badge, (cx + SLOT_SIZE - badge.get_width() - 2,
                           cy + SLOT_SIZE - badge.get_height() - 1))

    # hints at bottom of grid
    hints = ["WASD / arrows  navigate", "Left-click  equip", "Right-click  options"]
    hy = PAD + SH - PAD * 2 - len(hints) * (fXs.get_linesize() + 3) - 6
    for h in hints:
        hs = fXs.render(h, True, _TEXT_DIM)
        surf.blit(hs, (grid_x + GRID_W // 2 - hs.get_width() // 2, hy))
        hy += fXs.get_linesize() + 3

    # ── CENTER: paper-doll ───────────────────────────────────────────────
    dy      = PAD + 10
    doll_cx = doll_x + DOLL_W // 2
    _blit_center(surf, fHdr, "EQUIPPED", _TEXT_BRIGHT, doll_cx, dy)
    dy += fHdr.get_linesize() + 6
    pygame.draw.line(surf, _BORDER, (doll_x + 6, dy), (doll_x + DOLL_W - 6, dy), 1)
    dy += 10

    equipped_weapon, equipped_armor, equipped_off_hand, \
        equipped_acc1, equipped_acc2 = player.get_equipped_items()

    EQ = 48   # equipment slot size
    EQ_GAP = 8

    # Player avatar — large, centered
    AVATAR_SIZE = 72
    avatar = _get_sprite(player.char, AVATAR_SIZE)
    # tint avatar with player color
    av_tinted = avatar.copy()
    av_x = doll_cx - AVATAR_SIZE // 2
    av_y = dy + EQ + EQ_GAP * 2
    surf.blit(av_tinted, (av_x, av_y))

    # Avatar border
    pygame.draw.rect(surf, _BORDER_LT,
                     (av_x - 4, av_y - 4, AVATAR_SIZE + 8, AVATAR_SIZE + 8),
                     1, border_radius=5)
    # Name under avatar
    ns = fSm.render(player.name, True, player.color)
    surf.blit(ns, (doll_cx - ns.get_width() // 2, av_y + AVATAR_SIZE + 4))
    cs = fXs.render(f"Lv {player.level}  {getattr(player, 'class_name', '')}", True, _TEXT_DIM)
    surf.blit(cs, (doll_cx - cs.get_width() // 2, av_y + AVATAR_SIZE + 4 + fSm.get_linesize() + 2))

    # Equipment slots arranged around the avatar:
    #   Weapon (top-left) | Armor (top-right)
    #   Off-hand (mid-left) | Acc1 (mid-right)
    #   Acc2 (bottom-center)

    left_x  = doll_x + PAD
    right_x = doll_x + DOLL_W - PAD - EQ
    top_y   = dy

    _draw_equip_slot(surf, equipped_weapon,   "Weapon",   left_x,  top_y, EQ, fXs)
    game._equip_slot_rects["weapon"]   = pygame.Rect(left_x,  top_y, EQ, EQ)
    _draw_equip_slot(surf, equipped_armor,    "Armor",    right_x, top_y, EQ, fXs)
    game._equip_slot_rects["armor"]    = pygame.Rect(right_x, top_y, EQ, EQ)

    mid_y = av_y + (AVATAR_SIZE - EQ) // 2
    _draw_equip_slot(surf, equipped_off_hand, "Off-hand", left_x,  mid_y, EQ, fXs)
    game._equip_slot_rects["off_hand"] = pygame.Rect(left_x,  mid_y, EQ, EQ)
    _draw_equip_slot(surf, equipped_acc1,     "Acc. 1",   right_x, mid_y, EQ, fXs)
    game._equip_slot_rects["acc1"]     = pygame.Rect(right_x, mid_y, EQ, EQ)

    bot_y = av_y + AVATAR_SIZE + fSm.get_linesize() + fXs.get_linesize() + 16
    acc2_x = doll_cx - EQ // 2
    _draw_equip_slot(surf, equipped_acc2, "Acc. 2", acc2_x, bot_y, EQ, fXs)
    game._equip_slot_rects["acc2"]     = pygame.Rect(acc2_x, bot_y, EQ, EQ)

    # Quick stats block
    qs_y = bot_y + EQ + fXs.get_linesize() + 18
    pygame.draw.line(surf, _BORDER, (doll_x + 6, qs_y - 6),
                     (doll_x + DOLL_W - 6, qs_y - 6), 1)

    hp_pct = player.hp / player.max_hp if player.max_hp else 0
    hp_col = _RED if hp_pct < 0.33 else _GOLD if hp_pct < 0.66 else _GREEN
    bar_w  = DOLL_W - PAD * 4
    bar_h  = 12
    bx     = doll_x + PAD * 2
    pygame.draw.rect(surf, (30, 30, 40), (bx, qs_y, bar_w, bar_h), border_radius=3)
    fw = max(0, int(bar_w * hp_pct))
    if fw: pygame.draw.rect(surf, hp_col, (bx, qs_y, fw, bar_h), border_radius=3)
    pygame.draw.rect(surf, _BORDER_LT, (bx, qs_y, bar_w, bar_h), 1, border_radius=3)
    hp_lbl = fXs.render(f"HP  {player.hp}/{player.max_hp}", True, _TEXT_BRIGHT)
    surf.blit(hp_lbl, (bx + bar_w // 2 - hp_lbl.get_width() // 2,
                       qs_y + bar_h // 2 - hp_lbl.get_height() // 2))
    qs_y += bar_h + 6

    for label, val, col in [
        ("AC",       player.armor_class,        _CYAN),
        ("Atk Bon",  f"+{player.attack_bonus}", _TEXT_NORMAL),
        ("Atk Power", f"{player.attack_power}", _TEXT_NORMAL),
        ("Spell Bon", f"+{player.spell_bonus}",  _TEXT_NORMAL),
        ("Gold",     f"{player.gold} gp",       _GOLD),
    ]:
        _blit(surf, fXs, label, _TEXT_DIM, bx, qs_y)
        vs = fXs.render(str(val), True, col)
        surf.blit(vs, (bx + bar_w - vs.get_width(), qs_y))
        qs_y += fXs.get_linesize() + 4

    qs_y = bot_y + EQ + fXs.get_linesize() + 140
    pygame.draw.line(surf, _BORDER, (doll_x + 6, qs_y - 6),
                     (doll_x + DOLL_W - 6, qs_y - 6), 1)

    fHdr = _f(19, bold=True)
    fSm  = _f(12)
    fBig = _f(17, bold=True)
    content_y = PAD + 440    
    col_w     = DOLL_W - PAD * 2
    col1_x    = PAD * 4 + GRID_W    
    y1 = content_y + 6
    BOX  = 60; GAP = 6
    bx0  = col1_x + (col_w - (3 * BOX + 2 * GAP)) // 2
    for row in range(2):
        for col in range(3):
            idx = row * 3 + col
            attrs = [
                ("STR", player.strength,     player.get_ability_modifier(player.strength)),
                ("DEX", player.dexterity,    player.get_ability_modifier(player.dexterity)),
                ("CON", player.constitution, player.get_ability_modifier(player.constitution)),
                ("INT", player.intelligence, player.get_ability_modifier(player.intelligence)),
                ("WIS", player.wisdom,       player.get_ability_modifier(player.wisdom)),
                ("CHA", player.charisma,     player.get_ability_modifier(player.charisma)),
            ]
            if idx >= len(attrs): break
            _stat_box(surf, fBig, fSm, attrs[idx][0], attrs[idx][1], attrs[idx][2],
                      bx0 + col * (BOX + GAP),
                      y1  + row * (BOX + fSm.get_linesize() + GAP + 6), BOX)    

    # ── RIGHT: detail card ───────────────────────────────────────────────
    _draw_detail_card(surf, sel_item,
                      detail_x + 2, PAD + 2,
                      DETAIL_W - 4, SH - PAD * 2 - 4)


# ═══════════════════════════════════════════════════════════════════════════════
# INVENTORY ACTION POPUP
# ═══════════════════════════════════════════════════════════════════════════════
def render_inventory_menu_popup(game):
    if not game.selected_inventory_item:
        return
    item  = game.selected_inventory_item
    fSec  = _f(16, bold=True)
    fInfo = _f(14)
    fSm   = _f(12)
    PW, PH = 230, 195
    surf   = game.inventory_ui_surface
    px = surf.get_width()  // 2 - PW // 2
    py = surf.get_height() // 2 - PH // 2

    popup = pygame.Surface((PW, PH), pygame.SRCALPHA)
    popup.fill((12, 12, 18, 245))
    pygame.draw.rect(popup, _BORDER_LT, popup.get_rect(), 1, border_radius=7)

    # sprite + name
    sp = _get_sprite(item.char, 32)
    popup.blit(sp, (PW // 2 - 16, 10))
    ns = fSec.render(item.name, True, item.color)
    if ns.get_width() > PW - 16:
        ns = _f(11, bold=True).render(item.name, True, item.color)
    popup.blit(ns, (PW // 2 - ns.get_width() // 2, 46))

    tc = _item_type_color(item)
    tl = fSm.render(_item_type_label(item), True, tc)
    popup.blit(tl, (PW // 2 - tl.get_width() // 2, 46 + fSec.get_linesize() + 1))
    pygame.draw.line(popup, _BORDER, (12, 80), (PW - 12, 80), 1)

    y = 88
    for label, is_cancel in [
        ("[U]  Use",           False),
        ("[E]  Equip / Unequip", False),
        ("[D]  Drop",          False),
        ("[Q/F]  Quick Bar",   False),
        ("[C]  Cancel",        True),
    ]:
        is_use = "Use" in label and isinstance(item, CampfireKit)
        col    = _GREEN if is_use else _TEXT_DIM if is_cancel else _TEXT_NORMAL
        ls     = fInfo.render(label, True, col)
        popup.blit(ls, (PW // 2 - ls.get_width() // 2, y))
        y += fInfo.get_linesize() + 5

    game.screen.blit(popup, (px, py))


# ═══════════════════════════════════════════════════════════════════════════════
# CHARACTER SHEET  (DnD-style)
# ═══════════════════════════════════════════════════════════════════════════════
def render_character_menu(game):
    surf = game.inventory_ui_surface
    surf.fill((0, 0, 0, 0))
    player  = game.player
    SW = surf.get_width()
    SH = surf.get_height()
    PAD  = 14

    fHdr = _f(19, bold=True)
    fSec = _f(16, bold=True)
    fN   = _f(14)
    fSm  = _f(12)
    fBig = _f(17, bold=True)

    pygame.draw.rect(surf, _BG, (0, 0, SW, SH))
    pygame.draw.rect(surf, _BORDER, (PAD, PAD, SW - PAD*2, SH - PAD*2), 1, border_radius=4)

    title_rect = pygame.Rect(PAD, PAD, SW - PAD*2, 36)
    pygame.draw.rect(surf, _BG_PANEL, title_rect)
    pygame.draw.rect(surf, _ACCENT_GOLD, title_rect, 1)
    _blit_center(surf, fHdr, "CHARACTER  SHEET", _GOLD, SW // 2, PAD + 8)

    content_y = PAD + 44
    content_h = SH - content_y - PAD
    col_w     = (SW - PAD * 4) // 3
    col1_x    = PAD * 2
    col2_x    = col1_x + col_w + PAD
    col3_x    = col2_x + col_w + PAD

    for cx in (col1_x, col2_x, col3_x):
        r = pygame.Rect(cx - 6, content_y, col_w + 8, content_h)
        pygame.draw.rect(surf, _BG_PANEL, r, border_radius=4)
        pygame.draw.rect(surf, _BORDER,   r, 1, border_radius=4)

    # ── Column 1: Identity + Ability Scores ──────────────────────────────
    y1 = content_y + 8
    y1 = _section_label(surf, fSec, "IDENTITY", col1_x, y1, col_w)
    race_name = getattr(player.race, "name", "Unknown") if hasattr(player, "race") else "Unknown"
    for label, val in [
        ("Name",  player.name),
        ("Class", getattr(player, "class_name", "?")),
        ("Race",  race_name),
        ("Level", player.level),
        ("XP",    f"{player.current_xp} / {player.xp_to_next_level}"),
        ("Gold",  f"{player.gold} gp"),
    ]:
        _blit(surf, fSm, label, _TEXT_DIM, col1_x, y1)
        vs = fN.render(str(val), True, _TEXT_BRIGHT)
        surf.blit(vs, (col1_x + col_w - vs.get_width(), y1))
        y1 += fN.get_linesize() + 3
        pygame.draw.line(surf, _BORDER, (col1_x, y1), (col1_x + col_w, y1), 1)
        y1 += 3
    y1 += 8
    y1 = _section_label(surf, fSec, "ABILITY SCORES", col1_x, y1, col_w)

    BOX  = 52; GAP = 6
    bx0  = col1_x + (col_w - (3 * BOX + 2 * GAP)) // 2
    for row in range(2):
        for col in range(3):
            idx = row * 3 + col
            attrs = [
                ("STR", player.strength,     player.get_ability_modifier(player.strength)),
                ("DEX", player.dexterity,    player.get_ability_modifier(player.dexterity)),
                ("CON", player.constitution, player.get_ability_modifier(player.constitution)),
                ("INT", player.intelligence, player.get_ability_modifier(player.intelligence)),
                ("WIS", player.wisdom,       player.get_ability_modifier(player.wisdom)),
                ("CHA", player.charisma,     player.get_ability_modifier(player.charisma)),
            ]
            if idx >= len(attrs): break
            _stat_box(surf, fBig, fSm, attrs[idx][0], attrs[idx][1], attrs[idx][2],
                      bx0 + col * (BOX + GAP),
                      y1  + row * (BOX + fSm.get_linesize() + GAP + 6), BOX)

    # ── Column 2: Combat + Saving Throws + Proficiencies ─────────────────
    y2 = content_y + 8
    y2 = _section_label(surf, fSec, "COMBAT", col2_x, y2, col_w)
    hp_pct = player.hp / player.max_hp if player.max_hp else 0
    hp_col = _RED if hp_pct < 0.33 else _GOLD if hp_pct < 0.66 else _GREEN
    bar_h  = 14
    pygame.draw.rect(surf, (30, 30, 40), (col2_x, y2, col_w, bar_h), border_radius=3)
    fw = max(0, int(col_w * hp_pct))
    if fw: pygame.draw.rect(surf, hp_col, (col2_x, y2, fw, bar_h), border_radius=3)
    pygame.draw.rect(surf, _BORDER_LT, (col2_x, y2, col_w, bar_h), 1, border_radius=3)
    hp_s = fSm.render(f"HP  {player.hp}/{player.max_hp}", True, _TEXT_BRIGHT)
    surf.blit(hp_s, (col2_x + col_w // 2 - hp_s.get_width() // 2,
                     y2 + bar_h // 2 - hp_s.get_height() // 2))
    y2 += bar_h + 8
    for label, val in [
        ("Armor Class",       player.armor_class),
        ("Initiative",        f"+{player.get_ability_modifier(player.dexterity)}"),
        ("Proficiency Bonus", f"+{player.proficiency_bonus}"),
        ("Attack Bonus",      f"+{player.attack_bonus}"),
        ("Attack Power",      f"+{player.attack_power}"),
        ("Spell Bonus",       f"+{player.spell_bonus}"),
    ]:
        _blit(surf, fSm, label, _TEXT_DIM, col2_x, y2)
        vs = fN.render(str(val), True, _CYAN)
        surf.blit(vs, (col2_x + col_w - vs.get_width(), y2))
        y2 += fN.get_linesize() + 4
    y2 += 8
    y2 = _section_label(surf, fSec, "SAVING THROWS", col2_x, y2, col_w)
    for name, bonus, prof in [
        ("Strength",     player.get_saving_throw_bonus("STR"), player.saving_throw_proficiencies["STR"]),
        ("Dexterity",    player.get_saving_throw_bonus("DEX"), player.saving_throw_proficiencies["DEX"]),
        ("Constitution", player.get_saving_throw_bonus("CON"), player.saving_throw_proficiencies["CON"]),
        ("Intelligence", player.get_saving_throw_bonus("INT"), player.saving_throw_proficiencies["INT"]),
        ("Wisdom",       player.get_saving_throw_bonus("WIS"), player.saving_throw_proficiencies["WIS"]),
        ("Charisma",     player.get_saving_throw_bonus("CHA"), player.saving_throw_proficiencies["CHA"]),
    ]:
        y2 = _save_row(surf, fSm, name, bonus, prof, col2_x, y2, col_w)
    y2 += 8
    y2 = _section_label(surf, fSec, "PROFICIENCIES", col2_x, y2, col_w)
    all_profs = (getattr(player, "skill_proficiencies", []) +
                 getattr(player, "weapon_proficiencies", []) +
                 getattr(player, "armor_proficiencies", []))
    if all_profs:
        _blit_wrap(surf, fSm, ", ".join(all_profs), _TEXT_NORMAL, col2_x, y2, col_w)
    else:
        _blit(surf, fSm, "None", _TEXT_DIM, col2_x, y2)

    # ── Column 3: Equipment + Effects + Resistances ───────────────────────
    y3 = content_y + 8
    y3 = _section_label(surf, fSec, "EQUIPMENT", col3_x, y3, col_w)
    equipped_weapon, equipped_armor, equipped_off_hand, \
        equipped_acc1, equipped_acc2 = player.get_equipped_items()
    for slot_label, item in [
        ("Weapon",   equipped_weapon),
        ("Armor",    equipped_armor),
        ("Off-hand", equipped_off_hand),
        ("Acc. 1",   equipped_acc1),
        ("Acc. 2",   equipped_acc2),
    ]:
        _blit(surf, fSm, slot_label, _TEXT_DIM, col3_x, y3)
        val = item.name if item else "— empty —"
        col = item.color if item else _TEXT_DIM
        vl  = fSm.render(val if len(val) < 22 else val[:21] + "...", True, col)
        surf.blit(vl, (col3_x + col_w - vl.get_width(), y3))
        y3 += fSm.get_linesize() + 3
        pygame.draw.line(surf, _BORDER, (col3_x, y3), (col3_x + col_w, y3), 1)
        y3 += 4
    y3 += 8
    y3 = _section_label(surf, fSec, "STATUS EFFECTS", col3_x, y3, col_w)
    effects = getattr(player, "active_status_effects", [])
    if not effects:
        _blit(surf, fSm, "None", _TEXT_DIM, col3_x, y3)
        y3 += fSm.get_linesize() + 4
    else:
        for eff in effects:
            turns = getattr(eff, "turns_left", "?")
            tag   = f"{eff.name}  ({turns}t)"
            ts    = fSm.render(tag, True, _ORANGE)
            tw    = ts.get_width() + 10
            pygame.draw.rect(surf, (35, 22, 10), (col3_x, y3, tw, ts.get_height() + 4), border_radius=3)
            pygame.draw.rect(surf, _ORANGE,      (col3_x, y3, tw, ts.get_height() + 4), 1, border_radius=3)
            surf.blit(ts, (col3_x + 5, y3 + 2))
            y3 += ts.get_height() + 8
    y3 += 4
    y3 = _section_label(surf, fSec, "DAMAGE RESISTANCES", col3_x, y3, col_w)
    resistances = getattr(player, "damage_resistances", [])
    if resistances:
        _blit_wrap(surf, fSm, ", ".join(resistances), _GREEN, col3_x, y3, col_w)
    else:
        _blit(surf, fSm, "None", _TEXT_DIM, col3_x, y3)

    hint = fSm.render("C  close   |   I  inventory", True, _TEXT_DIM)
    surf.blit(hint, (SW // 2 - hint.get_width() // 2, SH - PAD - hint.get_height()))