import pygame
from items.items import CampfireKit

# ── Palette ──────────────────────────────────────────────────────────────────
_BG          = (10,   8,  10)   # near-black stone
_BG_PANEL    = (18,  14,  18)   # aged obsidian
_BG_ROW_ALT  = (24,  18,  22)   # worn dark granite

_BG_SELECTED = (52,  32,  36)   # blood-tinted selection

_BORDER      = (50,  40,  44)   # dark iron
_BORDER_LT   = (78,  64,  68)   # worn steel highlight

_ACCENT      = (96,  38,  38)   # dried blood crimson
_ACCENT_GOLD = (118,  88,  34)  # tarnished brass

_TEXT_DIM    = (112, 102,  96)  # dusty parchment
_TEXT_NORMAL = (188, 178, 168)  # aged bone
_TEXT_BRIGHT = (232, 224, 210)  # candlelit ivory

_GOLD        = (164, 124,  52)  # old gold relic
_CYAN        = ( 72, 132, 136)  # spectral teal
_GREEN       = ( 74, 122,  76)  # swamp herb green

_RED         = (148,  42,  42)  # coagulated blood
_ORANGE      = (176,  96,  42)  # ember glow

# ── Font helpers ─────────────────────────────────────────────────────────────
def _f(size, bold=False):
    try:    return pygame.font.SysFont("consolas", size, bold=bold)
    except: return pygame.font.Font(None, size + 20)

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

def _divider(surf, x, y, w, color=_BORDER):
    pygame.draw.line(surf, color, (x, y), (x + w, y), 1)
    return y + 6

def _section_label(surf, font, label, x, y, w):
    h = font.get_linesize()
    pygame.draw.rect(surf, _ACCENT, (x, y + 2, 3, h - 2))
    _blit(surf, font, label, _TEXT_BRIGHT, x + 8, y)
    pygame.draw.line(surf, _BORDER, (x, y + h + 3), (x + w, y + h + 3), 1)
    return y + h + 9

def _stat_box(surf, font_big, font_small, label, score, modifier, x, y, size=50):
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

def _save_row(surf, font, label, bonus, proficient, x, y, w):
    dot_color = _GREEN if proficient else _TEXT_DIM
    pygame.draw.circle(surf, dot_color, (x + 5, y + font.get_linesize() // 2), 4)
    _blit(surf, font, label, _TEXT_NORMAL, x + 14, y)
    mod_str = f"+{bonus}" if bonus >= 0 else str(bonus)
    bs = font.render(mod_str, True, _GREEN if proficient else _TEXT_DIM)
    surf.blit(bs, (x + w - bs.get_width(), y))
    return y + font.get_linesize() + 3


# ═══════════════════════════════════════════════════════════════════════════
# INVENTORY SCREEN
# ═══════════════════════════════════════════════════════════════════════════
def render_inventory_screen(game):
    surf = game.inventory_ui_surface
    surf.fill((0, 0, 0, 0))
    player   = game.player
    SW  = surf.get_width() 
    SH  = surf.get_height()
    PAD = 12

    L_W = int(SW * 0.55)
    R_X = L_W + PAD * 2
    R_W = SW - R_X - PAD

    fHdr  = _f(18, bold=True)
    fSec  = _f(16, bold=True)
    fInfo = _f(14)
    fSm   = _f(14)
    ROW_H = fInfo.get_linesize() + 8

    # panels
    left_rect  = pygame.Rect(PAD, PAD, L_W - PAD, SH - PAD * 2)
    right_rect = pygame.Rect(R_X, PAD, R_W, SH - PAD * 2)
    pygame.draw.rect(surf, _BG_PANEL, left_rect,  border_radius=6)
    pygame.draw.rect(surf, _BORDER,   left_rect,  1, border_radius=6)
    pygame.draw.rect(surf, _BG_PANEL, right_rect, border_radius=6)
    pygame.draw.rect(surf, _BORDER,   right_rect, 1, border_radius=6)

    # left header
    y  = PAD + 10
    lx = PAD * 2
    _blit(surf, fHdr, "INVENTORY", _TEXT_BRIGHT, lx, y)
    cap_s = fSm.render(f"{len(player.inventory.items)}/{player.inventory.capacity}", True, _GOLD)
    surf.blit(cap_s, (left_rect.right - cap_s.get_width() - 8, y + 2))
    y += fHdr.get_linesize() + 4
    y  = _divider(surf, lx, y, L_W - PAD * 3)

    # item rows
    if not player.inventory.items:
        _blit(surf, fSm, "— empty —", _TEXT_DIM, lx, y + 10)
    else:
        for i, item in enumerate(player.inventory.items):
            selected = (i == game.selected_inventory_index)
            row_rect = pygame.Rect(lx - 4, y, L_W - PAD * 2, ROW_H)
            if selected:
                pygame.draw.rect(surf, _BG_SELECTED, row_rect, border_radius=3)
                pygame.draw.rect(surf, _ACCENT,      row_rect, 1, border_radius=3)
            elif i % 2 == 0:
                pygame.draw.rect(surf, _BG_ROW_ALT, row_rect, border_radius=3)

            badge = fSm.render(str((i + 1) % 10), True, _CYAN if selected else _TEXT_DIM)
            surf.blit(badge, (lx, y + ROW_H // 2 - badge.get_height() // 2))

            name_color = (255, 255, 100) if selected else item.color
            name = item.name if len(item.name) < 32 else item.name[:31] + "..."
            ns   = fInfo.render(name, True, name_color)
            surf.blit(ns, (lx + 20, y + ROW_H // 2 - ns.get_height() // 2))

            itype = getattr(item, "item_type", type(item).__name__)
            ts    = fSm.render(itype, True, _TEXT_DIM)
            surf.blit(ts, (left_rect.right - ts.get_width() - 8,
                           y + ROW_H // 2 - ts.get_height() // 2))
            y += ROW_H + 2

    # right: equipped
    rx = R_X + PAD
    ry = PAD + 10
    rw = R_W - PAD * 2
    ry = _section_label(surf, fSec, "EQUIPPED", rx, ry, rw)

    equipped_weapon, equipped_armor, equipped_off_hand, \
        equipped_acc1, equipped_acc2 = player.get_equipped_items()

    for slot_label, item in [
        ("Weapon",   equipped_weapon),
        ("Armor",    equipped_armor),
        ("Off-hand", equipped_off_hand),
        ("Acc. 1",   equipped_acc1),
        ("Acc. 2",   equipped_acc2),
    ]:
        sl = fSm.render(slot_label, True, _TEXT_DIM)
        surf.blit(sl, (rx, ry))
        val = item.name if item else "—"
        col = item.color if item else _TEXT_DIM
        vl  = fInfo.render(val, True, col)
        surf.blit(vl, (rx + rw - vl.get_width(), ry))
        ry += fInfo.get_linesize() + 5
        pygame.draw.line(surf, _BORDER, (rx, ry), (rx + rw, ry), 1)
        ry += 4

    ry += 8
    ry = _section_label(surf, fSec, "STATS", rx, ry, rw)

    hp_pct = player.hp / player.max_hp if player.max_hp else 0
    hp_col = _RED if hp_pct < 0.33 else _GOLD if hp_pct < 0.66 else _GREEN
    for label, val, col in [
        ("HP",       f"{player.hp}/{player.max_hp}", hp_col),
        ("AC",       player.armor_class,        _CYAN),
        ("Atk Bon",  f"+{player.attack_bonus}", _TEXT_NORMAL),
        ("Atk Pow",  f"+{player.attack_power}", _TEXT_NORMAL),
        ("Gold",     f"{player.gold} gp",       _GOLD),
    ]:
        _blit(surf, fSm, label, _TEXT_DIM, rx, ry)
        vs = fInfo.render(str(val), True, col)
        surf.blit(vs, (rx + rw - vs.get_width(), ry))
        ry += fInfo.get_linesize() + 5

    # hints
    hints  = ["Up/Down  navigate", "Enter  select", "I  close"]
    hint_y = right_rect.bottom - len(hints) * (fSm.get_linesize() + 3) - 8
    for h in hints:
        hs = fSm.render(h, True, _TEXT_DIM)
        surf.blit(hs, (rx + rw // 2 - hs.get_width() // 2, hint_y))
        hint_y += fSm.get_linesize() + 3


# ═══════════════════════════════════════════════════════════════════════════
# INVENTORY ACTION POPUP
# ═══════════════════════════════════════════════════════════════════════════
def render_inventory_menu_popup(game):
    if not game.selected_inventory_item:
        return
    item  = game.selected_inventory_item
    fSec  = _f(16, bold=True) 
    fInfo = _f(14)
    fSm   = _f(14)
    PW, PH = 240, 200
    surf   = game.inventory_ui_surface
    px = surf.get_width()  // 2 - PW // 2
    py = surf.get_height() // 2 - PH // 2

    popup = pygame.Surface((PW, PH), pygame.SRCALPHA)
    popup.fill((14, 14, 20, 240))
    pygame.draw.rect(popup, _BORDER_LT, popup.get_rect(), 1, border_radius=6)

    ns = fSec.render(item.name, True, item.color)
    popup.blit(ns, (PW // 2 - ns.get_width() // 2, 12))
    itype = getattr(item, "item_type", type(item).__name__)
    ts = fSm.render(itype, True, _TEXT_DIM)
    popup.blit(ts, (PW // 2 - ts.get_width() // 2, 12 + fSec.get_linesize() + 2))
    pygame.draw.line(popup, _BORDER, (12, 44), (PW - 12, 44), 1)

    y = 54
    for label, is_cancel in [
        ("[U]  Use",              False),
        ("[E]  Equip",            False),
        ("[D]  Drop",             False),
        ("[Q/F]  Quick Bar",      False),
        ("[C]  Cancel",           True),
    ]:
        is_use = "Use" in label and isinstance(item, CampfireKit)
        col    = _GREEN if is_use else _TEXT_DIM if is_cancel else _TEXT_NORMAL
        ls     = fInfo.render(label, True, col)
        popup.blit(ls, (PW // 2 - ls.get_width() // 2, y))
        y += fInfo.get_linesize() + 6

    game.screen.blit(popup, (px, py))


# ═══════════════════════════════════════════════════════════════════════════
# CHARACTER SHEET  (DnD-style)
# ═══════════════════════════════════════════════════════════════════════════
def render_character_menu(game):
    surf = game.inventory_ui_surface
    surf.fill((0, 0, 0, 0))
    player = game.player
    SW = surf.get_width()
    SH = surf.get_height()
    PAD  = 12

    fHdr = _f(20, bold=True)
    fSec = _f(16, bold=True)
    fN   = _f(14)
    fSm  = _f(14)
    fBig = _f(18, bold=True)

    # background
    pygame.draw.rect(surf, _BG, (0, 0, SW, SH))
    pygame.draw.rect(surf, _BORDER, (PAD, PAD, SW - PAD*2, SH - PAD*2), 1, border_radius=4)

    # title bar
    title_rect = pygame.Rect(PAD, PAD, SW - PAD*2, 36)
    pygame.draw.rect(surf, _BG_PANEL, title_rect)
    pygame.draw.rect(surf, _ACCENT_GOLD, title_rect, 1)
    _blit_center(surf, fHdr, "CHARACTER  SHEET", _GOLD, SW // 2, PAD + 8)

    content_y = PAD + 44
    content_h = SH - content_y - PAD
    col_w     = (SW - PAD * 4) // 3
    col1_x    = PAD * 1.2
    col2_x    = col1_x + col_w + PAD
    col3_x    = col2_x + col_w + PAD

    for cx in (col1_x, col2_x, col3_x):
        r = pygame.Rect(cx - 6, content_y, col_w + 8, content_h)
        pygame.draw.rect(surf, _BG_PANEL, r, border_radius=4)
        pygame.draw.rect(surf, _BORDER,   r, 1, border_radius=4)

    # ── COLUMN 1: Identity + Ability Scores ─────────────────────────────
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

    BOX  = 52
    GAP  = 6
    rw   = 3 * BOX + 2 * GAP
    bx0  = col1_x + (col_w - rw) // 2
    attrs = [
        ("STR", player.strength,     player.get_ability_modifier(player.strength)),
        ("DEX", player.dexterity,    player.get_ability_modifier(player.dexterity)),
        ("CON", player.constitution, player.get_ability_modifier(player.constitution)),
        ("INT", player.intelligence, player.get_ability_modifier(player.intelligence)),
        ("WIS", player.wisdom,       player.get_ability_modifier(player.wisdom)),
        ("CHA", player.charisma,     player.get_ability_modifier(player.charisma)),
    ]
    for row in range(2):
        for col in range(3):
            idx = row * 3 + col
            if idx >= len(attrs): break
            bx = bx0 + col * (BOX + GAP)
            by = y1  + row * (BOX + fSm.get_linesize() + GAP + 6)
            _stat_box(surf, fBig, fSm, attrs[idx][0], attrs[idx][1], attrs[idx][2], bx, by, BOX)

    # ── COLUMN 2: Combat + Saving Throws + Proficiencies ────────────────
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
        y2 = _blit_wrap(surf, fSm, ", ".join(all_profs), _TEXT_NORMAL, col2_x, y2, col_w)
    else:
        _blit(surf, fSm, "None", _TEXT_DIM, col2_x, y2)

    # ── COLUMN 3: Equipment + Effects + Resistances ─────────────────────
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
        sl = fSm.render(slot_label, True, _TEXT_DIM)
        surf.blit(sl, (col3_x, y3))
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

    # footer
    hint = fSm.render("C  close   |   I  inventory", True, _TEXT_DIM)
    surf.blit(hint, (SW // 2 - hint.get_width() // 2, SH - PAD - hint.get_height()))