"""Team coordination: rally on a shared camp target and avoid solo fights.

Each champion publishes the camp group it is heading for in shared memory, so a
second champion can join the first. Camps are only attacked once enough allies are
close to them, and enemy champions are only fought when we are not alone or outnumbered.
"""
import cambc

# ---- Tunables ---------------------------------------------------------------
PARTY_SINGLE = 2       # champions needed to take a camp group with one monster (2 vs 1)
PARTY_LARGE = 3        # champions needed for a group with several monsters (5 = whole team)
CAP_SINGLE = 2         # most champions that should converge on a one-monster camp
CAP_LARGE = max(5, isdraft())          # most champions that should converge on a large camp
RALLY_RELAX = 20       # turns waiting before the large-camp requirement drops by one
RALLY_GIVE_UP = 60     # turns waiting at a camp before trying a different one
BAN_ROUNDS = 40        # how long a given-up camp is avoided
STAGE_RADIUS = 5       # waiting distance from a camp (keep outside its attack range)
JOIN_RADIUS = STAGE_RADIUS + 3   # allies within this of a camp count as part of the party
MIN_ALLY_HEALTH = 0.30  # allies below this health fraction don't count as help
FINISH_HEALTH = 0.25    # a target below this health fraction may be finished off solo
THREAT_RADIUS = 9       # enemy champions this close count as a threat

# Shared memory: byte 16 counts claimed slots, then 2 bytes per slot (target+1, round stamp).
# Bytes 0-3 (round number) and 8-10 (role counts) are used elsewhere.
COORD_OFFSET = 16
MAX_SLOTS = 5
STALE_ROUNDS = 6        # a record older than this is ignored (champion dead or recalling)


def distance(a, b):
    return a.chebyshev_distance(b)


def tiles_around(position, radius):
    tiles = cambc.Bitboard()
    tiles.draw_chebyshev(position, radius)
    return tiles


# ---- Shared memory ------------------------------------------------------------
def claim_slot():
    buf = bytearray(1)
    cambc.shared_memory.read(COORD_OFFSET, buf)
    slot = buf[0] % MAX_SLOTS
    cambc.shared_memory.write(COORD_OFFSET, bytes([(buf[0] + 1) % 256]))
    return slot


def publish(slot, target):
    record = bytes([0 if target is None else target + 1, cambc.round_number() % 256])
    cambc.shared_memory.write(COORD_OFFSET + 1 + 2 * slot, record)


def commitments(slot):
    """Return {camp group index: [slots of other champions heading there]}."""
    buf = bytearray(2 * MAX_SLOTS)
    cambc.shared_memory.read(COORD_OFFSET + 1, buf)
    now = cambc.round_number() % 256
    found = {}
    for s in range(MAX_SLOTS):
        target, stamp = buf[2 * s], buf[2 * s + 1]
        if s != slot and target and (now - stamp) % 256 <= STALE_ROUNDS:
            found.setdefault(target - 1, []).append(s)
    return found


# ---- Camp helpers -------------------------------------------------------------
def group_of(bot, camp):
    spawn = camp.spawn_position()
    for i, entry in enumerate(bot.camp_layout):
        if entry[1].is_set(spawn):
            return i
    return None


def need_for(size, waited):
    base = PARTY_SINGLE if size <= 1 else PARTY_LARGE
    return max(PARTY_SINGLE, base - waited // RALLY_RELAX)


def party_near(me, anchor, radius):
    """Healthy champions (me included) within radius of the camp."""
    pos = me.position()
    count = 1 if distance(pos, anchor) <= radius else 0
    for ally in cambc.vision.champions(cambc.Team.ALLY):
        p = ally.position()
        if p != pos and distance(p, anchor) <= radius \
                and ally.health() > ally.max_health() * MIN_ALLY_HEALTH:
            count += 1
    return count


def staging_goals(anchor):
    # A ring just outside the camp: close enough to join quickly, far enough to be safe.
    return tiles_around(anchor, STAGE_RADIUS) & ~tiles_around(anchor, STAGE_RADIUS - 1)


def group_goals(bot, idx):
    tiles = bot.camp_layout[idx][1]
    return (tiles & ~cambc.vision.visible_tiles()) | (tiles & cambc.vision.camp_tiles())


# ---- Target selection ---------------------------------------------------------
def pick_target(bot, ids):
    now = cambc.round_number()
    pos = cambc.me().position()
    commits = commitments(bot.slot)
    usable = [i for i in ids if bot.banned.get(i, 0) <= now]
    if not usable:
        bot.banned.clear()
        usable = list(ids)

    def cap(i):
        return CAP_SINGLE if bot.group_meta[i][1] <= 1 else CAP_LARGE

    current = bot.target if bot.target in usable else None
    if current is not None and not commits.get(current):
        # Alone on my target: if a lower-numbered ally chose another camp, join them instead.
        for j in usable:
            owners = commits.get(j, [])
            if j != current and owners and min(owners) < bot.slot and len(owners) < cap(j):
                current = None
                break
    if current is not None:
        return current

    # Prefer a camp an ally is already heading to (with room), then the nearest one.
    return min(usable, key=lambda j: (
        len(commits.get(j, [])) >= cap(j),
        not commits.get(j),
        distance(pos, bot.group_meta[j][0]),
    ))


def clear_target(bot):
    bot.target = None
    bot.engaged = None
    bot.wait_turns = 0
    publish(bot.slot, None)


def coordinate(bot, ids):
    """Choose a camp group and return the goal tiles: the camp itself once the party
    is ready, otherwise a staging ring outside it where we wait for allies."""
    me = cambc.me()
    target = pick_target(bot, ids)
    if target != bot.target:
        bot.target, bot.wait_turns, bot.engaged = target, 0, None
    publish(bot.slot, target)

    anchor, size = bot.group_meta[target]
    need = bot.engaged_need if bot.engaged == target else need_for(size, bot.wait_turns)
    if party_near(me, anchor, JOIN_RADIUS) >= need:
        bot.engaged, bot.engaged_need, bot.wait_turns = target, need, 0
        return group_goals(bot, target)

    bot.engaged = None
    if distance(me.position(), anchor) <= STAGE_RADIUS + 1:
        bot.wait_turns += 1
        if bot.wait_turns >= RALLY_GIVE_UP:
            bot.banned[target] = cambc.round_number() + BAN_ROUNDS
            bot.target, bot.wait_turns = None, 0
    return staging_goals(anchor)
