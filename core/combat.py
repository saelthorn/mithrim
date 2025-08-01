def player_attack(player, monster, game):
    """Handle the player's attack on a monster."""
    if monster.alive:
        damage = player.attack_power  # Assume player has an attack_power attribute
        monster.hp -= damage
        print(f"{player.name} attacks {monster.name} for {damage} damage!")
        if monster.hp <= 0:
            xp_gained = monster.die()  # Monster dies and returns XP
            player.gain_xp(xp_gained)  # Award XP to the player
            game.draw_ui()  # Redraw the UI to reflect new XP