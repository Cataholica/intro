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

from Champion_strats import ROLE_RULES, identify, claim_role
import teamplay as tp
from bot import bot

DASH_REACH_BONUS = 5
SUSTAIN_DISCOUNT = 0.10  # sustain champions recall this much lower
SHARD_ITEMS = {
    "strength": Item.POWER_SHARD_OF_STRENGTH,
    "focus": Item.POWER_SHARD_OF_FOCUS,
    "health": Item.POWER_SHARD_OF_HEALTH,
}

def distance(a: cambc.Vec2, b: cambc.Vec2) -> int:
    return a.chebyshev_distance(b)


def tiles_around(position: cambc.Vec2, radius: int) -> cambc.Bitboard:
    tiles = cambc.Bitboard()
    tiles.draw_chebyshev(position, radius)
    return tiles


def blocked_tiles() -> cambc.Bitboard:
    # Combine terrain and visible occupants using native bitboard operations.
    blocked = (game_map.walls() | game_map.holes() | game_map.altars()
               | game_map.spawn_region(Team.ENEMY) | cambc.vision.champion_tiles()
               | cambc.vision.camp_tiles() | cambc.vision.teleport_tiles())
    blocked.set(cambc.me().position(), False)
    return blocked

def weakest_first(targets):
    # Finishing low-health targets first shortens fights and takes less damage.
    visible = [t for t in targets if t.is_visible()]
    return sorted(visible, key=lambda t: t.health())

def note_camp_kinds(bot):
    # Groups don't report their kind unseen, so remember where gem clusters spawn.
    for camp in cambc.vision.camps():
        if camp.is_visible() and camp.is_gem_cluster():
            bot.gem_tiles.set(camp.spawn_position(), True)

def move_towards_closest(goals: cambc.Bitboard) -> bool:
    me = cambc.me()
    origin = me.position()
    if not me.can_move() or goals.is_set(origin):
        return False

    # Only free goals or occupied camp tiles can seed the field.
    blocked = blocked_tiles()
    goals &= ~blocked | cambc.vision.camp_tiles()
    if goals.is_empty():
        return False
    if goals.count() == 1 and not blocked.is_set(goals.positions()[0]):
        return me.move_towards(goals.positions()[0])

    # Expand from the goals until our current tile is reached.
    field = cambc.DistanceField()
    field.compute_to(blocked & ~goals, goals, tiles_around(origin, 0), cambc.Bitboard())

    # Choose a reachable step with a smaller distance to the goal.
    reachable = blocked.reachable_tiles(origin, me.base_stats().base_move_speed)
    step = min([origin, *reachable.positions()], key=field.get)
    return step != origin and me.move_absolute(step)


def attack_first_in_range(targets: Sequence[cambc.Unit]) -> bool:
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

"""
def farm_camps(bot: "Bot") -> None:
    # Attack a camp already in range, otherwise move toward the nearest camp tiles.
    if attack_first_in_range(weakest_first(cambc.vision.camps())):
        return

    # Spawn locations never change. Cache their union, then remove only groups
    # we can currently see respawning. Keep unseen camps as exploration goals.
    if bot.camp_layout is None:
        spawns = cambc.Bitboard()
        groups = [(group, group.spawn_tiles()) for group in game_map.camp_groups()]
        for _, tiles in groups:
            spawns |= tiles
        bot.camp_layout = spawns, groups
    spawns, groups = bot.camp_layout
    goals = spawns.copy()
    visible = cambc.vision.visible_tiles()
    for group, tiles in groups:
        if not (tiles & visible).is_empty() and isinstance(group.state(), game_map.CampGroupRespawning):
            goals &= ~tiles

    # Fresh vision after movement may reveal a camp already in range.
    if move_towards_closest(goals):
        attack_first_in_range(weakest_first(cambc.vision.camps()))
 """
# New code?
def select_goals(bot):
    # Which camp groups are worth fighting now: gold first, then crystals and invasion.
    reach = bot.reach()
    inf = float("inf")
    goals, ids = camp_goals(bot, reach, False, False, skip=bot.gem_tiles)
    if not ids:
        goals, ids = camp_goals(bot, inf, False, False, skip=bot.gem_tiles)
    if ids:
        bot.idle_turns = max(0, bot.idle_turns - 1)
        return goals, ids

    bot.idle_turns += 1
    if bot.may_invade():
        for enemy_side, only in ((False, bot.gem_tiles), (True, bot.gem_tiles), (True, None)):
            goals, ids = camp_goals(bot, inf, enemy_side, False, only=only)
            if ids:
                return goals, ids
        return tiles_around(bot.enemy_home, SIEGE_RADIUS), []
    # Pre-position on camps we can see respawning.
    return camp_goals(bot, reach, False, True)[0], []


def attack_ready_camps(bot):
    # Only attack camps whose party is ready, or that are nearly dead.
    me = cambc.me()
    ready = []
    for camp in weakest_first(cambc.vision.camps()):
        idx = tp.group_of(bot, camp)
        if idx is None:
            continue
        anchor, size = bot.group_meta[idx]
        need = bot.engaged_need if bot.engaged == idx else tp.need_for(size, 0)
        finishing = camp.health() < camp.max_health() * tp.FINISH_HEALTH
        if finishing or tp.party_near(me, anchor, tp.JOIN_RADIUS) >= need:
            ready.append(camp)
    return attack_first_in_range(ready)


def farm_camps(bot):
    note_camp_kinds(bot)
    if bot.camp_layout is None:
        build_layout(bot)
    if attack_ready_camps(bot):
        return

    goals, ids = select_goals(bot)
    if ids:
        goals = tp.coordinate(bot, ids)
    else:
        tp.clear_target(bot)

    # Fresh vision after movement may reveal a camp already in range.
    if move_towards_closest(goals):
        attack_ready_camps(bot)


def regroup_goals(me):
    # Run toward allies if any are visible, otherwise back to spawn.
    goals = cambc.Bitboard()
    for ally in cambc.vision.champions(Team.ALLY):
        if ally.position() != me.position():
            goals |= tiles_around(ally.position(), 2)
    if goals.is_empty():
        goals = game_map.spawn_region(Team.ALLY).copy()
    return goals


def handle_enemies(bot):
    # Fight enemy champions only as a group; otherwise regroup instead of trading 1v1.
    me = cambc.me()
    pos = me.position()
    near = [e for e in weakest_first(cambc.vision.champions(Team.ENEMY))
            if distance(pos, e.position()) <= tp.THREAT_RADIUS]
    if not near:
        return False
    allies = 1 + sum(1 for a in cambc.vision.champions(Team.ALLY)
                     if a.position() != pos
                     and distance(pos, a.position()) <= tp.THREAT_RADIUS
                     and a.health() > a.max_health() * tp.MIN_ALLY_HEALTH)
    if allies >= 2 and allies >= len(near):
        return attack_first_in_range(near)
    weak = [e for e in near if e.health() < e.max_health() * tp.FINISH_HEALTH]
    if weak and attack_first_in_range(weak):
        return True
    if me.can_move() and move_towards_closest(regroup_goals(me)):
        return True
    return attack_first_in_range(near)  # cornered: hit back
 
def build_layout(bot):
    # Spawn locations never change, so compute this once per champion.
    # Each entry: (group, spawn tiles, distance to our home, distance to enemy home).
    groups = []
    bot.group_meta = []
    for group in game_map.camp_groups():
        tiles = group.spawn_tiles()
        if tiles.is_empty():
            continue
        anchor = tiles.positions()[0]
        groups.append((group, tiles, distance(bot.home, anchor), distance(bot.enemy_home, anchor)))
        bot.group_meta.append((anchor, tiles.count()))
    bot.camp_layout = groups
 
"""
def camp_goals(bot, reach, enemy_side, respawning):
    # Union of spawn tiles for camp groups matching the filters.
    # Unseen groups count as "not respawning", so they stay as exploration goals.
    visible = cambc.vision.visible_tiles()
    occupied = cambc.vision.camp_tiles()
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
"""
def camp_goals(bot, reach, enemy_side, respawning, only=None, skip=None):
    visible = cambc.vision.visible_tiles()
    occupied = cambc.vision.camp_tiles()
    goals = cambc.Bitboard()
    ids = []
    for i, (group, tiles, d_home, d_enemy) in enumerate(bot.camp_layout):
        if (d_enemy < d_home) != enemy_side:
            continue
        if not enemy_side and d_home > reach:
            continue
        t = tiles
        if only is not None:
            t = t & only
        if skip is not None:
            t = t & ~skip
        if t.is_empty():
            continue
        is_respawning = (not (tiles & visible).is_empty()
                         and isinstance(group.state(), game_map.CampGroupRespawning))
        if is_respawning != respawning:
            continue
        if respawning:
            goals |= t
        else:
            # Skip visible spawn tiles with no camp on them; they're already dead.
            part = (t & ~visible) | (t & occupied)
            if not part.is_empty():
                goals |= part
                ids.append(i)
    return goals, ids
    
def recall_threshold(bot, trip_turns):
    # Early in a trip, push until nearly dead. Once the respawn window is close,
    # recall at moderate damage so shopping and the walk back line up with respawns.
    rules = bot.rules
    early = trip_turns < RESPAWN_MIN - RECALL_LEAD
    base = rules.hard_recall if early else rules.timed_recall
    if bot.profile.sustain:
        base -= SUSTAIN_DISCOUNT
    return max(0.05, base)
