# ---- Tunables ---------------------------------------------------------------
RESPAWN_MIN = 40            # camps start respawning this many turns after a clear
RECALL_LEAD = 8             # begin timed recalls this much earlier (channel + walk back)
HARD_RECALL_HEALTH = 0.20   # always recall below this when away from spawn
TIMED_RECALL_HEALTH = 0.60  # inside the respawn window, recall below this
BASE_REACH = 10             # starting farm radius (Chebyshev) around home
REACH_PER_TRIP = 3          # extra radius per completed recall
REACH_PER_SHARD = 1.5       # extra radius per power shard bought
INVADE_IDLE_TURNS = 15      # idle turns before invading (shrinks as shards are bought)
INVADE_MIN_IDLE = 3
SIEGE_RADIUS = 7            # where to loiter if no enemy camps are left to take

# Basically improvements to the camp farming function in bot.py, might merge the code into bot.py in the future
# After all, some functions depend on ones defined in bot.py
# We'll see how this works, too tired to check the code rn
# The code might be better improved with deeper knowledge of the API, but this will do for now.
def weakest_first(targets):
    # Finishing low-health targets first shortens fights and takes less damage.
    visible = [t for t in targets if t.is_visible()]
    return sorted(visible, key=lambda t: t.health())
 
 
def attack_first_in_range(targets):
    # Compute the attack mask once, rather than once per visible target.
    me = cambc.me()
    if not targets or not me.can_attack():
        return False
    attack_tiles = me.attack_tiles()
    for target in targets:
        if target.is_visible() and attack_tiles.is_set(target.position()) and target.health() > 0:
            me.attack(target)
            return True
    return False
 
 
def build_layout(bot):
    # Spawn locations never change, so compute this once per champion.
    # Each entry: (group, spawn tiles, distance to our home, distance to enemy home).
    groups = []
    for group in game_map.camp_groups():
        tiles = group.spawn_tiles()
        if tiles.is_empty():
            continue
        anchor = tiles.positions()[0]
        groups.append((group, tiles, distance(bot.home, anchor), distance(bot.enemy_home, anchor)))
    bot.camp_layout = groups
 
 
def camp_goals(bot, reach, enemy_side, respawning):
    # Union of spawn tiles for camp groups matching the filters.
    # Unseen groups count as "not respawning", so they stay as exploration goals.
    visible = cambc.vision.visible_tiles()
    goals = cambc.Bitboard()
    for group, tiles, d_home, d_enemy in bot.camp_layout:
        if (d_enemy < d_home) != enemy_side:
            continue
        if not enemy_side and d_home > reach:
            continue
        is_respawning = (not (tiles & visible).is_empty()
                         and isinstance(group.state(), game_map.CampGroupRespawning))
        if is_respawning == respawning:
            goals |= tiles
    return goals
 
 
def farm_camps(bot):
    # Attack a camp already in range, otherwise move toward the next ring of camps.
    if attack_first_in_range(weakest_first(cambc.vision.camps())):
        return
 
    if bot.camp_layout is None:
        build_layout(bot)
    reach = bot.reach()
 
    # 1. Farm: nearest live or unseen camps inside the current reach.
    goals = camp_goals(bot, reach, enemy_side=False, respawning=False)
    if not goals.is_empty():
        bot.idle_turns = max(0, bot.idle_turns - 1)
    else:
        # 2. Idle: everything nearby is cleared.
        bot.idle_turns += 1
        if bot.may_invade():
            goals = camp_goals(bot, reach, enemy_side=True, respawning=False)
            if goals.is_empty():
                goals = tiles_around(bot.enemy_home, SIEGE_RADIUS)
        else:
            # Pre-position on camps we can see respawning so we strike on spawn.
            goals = camp_goals(bot, reach, enemy_side=False, respawning=True)
 
    # Fresh vision after movement may reveal a camp already in range.
    if move_towards_closest(goals):
        attack_first_in_range(weakest_first(cambc.vision.camps()))
 
 
def recall_threshold(trip_turns):
    # Early in a trip, push until nearly dead. Once the respawn window is close,
    # recall at moderate damage so shopping and the walk back line up with respawns.
    if trip_turns < RESPAWN_MIN - RECALL_LEAD:
        return HARD_RECALL_HEALTH
    return TIMED_RECALL_HEALTH
