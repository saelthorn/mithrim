# TODO: Rework Boss Attacks to Reduce Spamming

## Steps:
1. [x] Add `attack_cooldown` and `telegraph_timer` attributes to Monster class __init__.
2. [x] Modify `attack` method: For bosses, check cooldown; if ready, telegraph and set timers; else, do normal attack.
3. [x] Modify `take_turn` method: Decrement timers; process telegraphed damage when telegraph_timer reaches 0.
4. [x] Test boss encounters to ensure balanced telegraph frequency and 3-turn delay.
