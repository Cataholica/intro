#Champion profiles: who each champion is and how it should play.
# Temporary template from the old game theory notes, but easily changed later

import cambc

CARRY, FLEX, SUPPORT = "carry", "flex", "support"

# Team shape from the notes: one hyper carry, three flex, one support.
# Change to {CARRY: 2, FLEX: 2, SUPPORT: 1} once teamplay coordination improves.
ROLE_CAPS = {CARRY: 1, FLEX: 3, SUPPORT: 1}
ROLE_INDEX = {CARRY: 0, FLEX: 1, SUPPORT: 2}
ROLE_OFFSET = 8  # shared-memory bytes 8..10 hold how many champions claimed each role


class Rules:

    def __init__(self, item_cap, hard_recall, timed_recall, reach_scale, invade_shards):
        self.item_cap = item_cap            # max shards this champion buys (None = unlimited)
        self.hard_recall = hard_recall      # recall below this health fraction early in a trip
        self.timed_recall = timed_recall    # recall below this once the respawn window is near
        self.reach_scale = reach_scale      # multiplier on farming radius
        self.invade_shards = invade_shards  # shards needed before this champion invades


ROLE_RULES = {
    # Never wants to die and soaks up all spare gold; stays closer to home until strong.
    CARRY:   Rules(item_cap=None, hard_recall=0.40, timed_recall=0.70, reach_scale=0.7, invade_shards=12),
    # Mid items, farms wide, invades when idle.
    FLEX:    Rules(item_cap=14, hard_recall=0.25, timed_recall=0.60, reach_scale=1.0, invade_shards=4),
    # Few items so the carry gets the gold; roams far and takes space early.
    SUPPORT: Rules(item_cap=6, hard_recall=0.20, timed_recall=0.50, reach_scale=1.3, invade_shards=0),
}


class Profile:
    def __init__(self, name, roles, build, dash=False, sustain=False):
        self.name = name        # must match the bytes submitted in the draft
        self.roles = roles      # preferred roles, best first
        self.build = build      # shard weights: {"strength": s, "focus": f, "health": h}
        self.dash = dash        # can dash: clears far camps safely, so farms farther out
        self.sustain = sustain  # heal/shield: can stay out longer before recalling


def _p(name, roles, s, f, h, **kw):
    return Profile(name, roles, {"strength": s, "focus": f, "health": h}, **kw)


# Builds follow the notes: health is the cheapest stat, damage moderate, focus the most
# expensive, so only focus-scaling casters lean on focus.
PROFILES = {p.name: p for p in (
    _p("CASSI_AND_ISSAC", (CARRY, SUPPORT),         0, 3, 2),  # best focus scaling in the game
    _p("VARG",            (FLEX, SUPPORT),          2, 0, 3, sustain=True),
    _p("REN",             (FLEX, SUPPORT, CARRY),   2, 0, 3, dash=True),
    _p("STELLAR",         (FLEX, CARRY),            0, 3, 1),  # strongest burst, needs few items
    _p("TAVI",            (FLEX, SUPPORT),          2, 0, 3),
    _p("WILLOW",          (SUPPORT, FLEX),          1, 0, 3, sustain=True),
    _p("VENDETTA",        (CARRY, FLEX),            3, 0, 1),  # ranged AD carry
    _p("RYTH",            (FLEX, SUPPORT),          2, 0, 2),
    _p("PRISM",           (FLEX, CARRY, SUPPORT),   0, 3, 2),
    _p("MARCELLA",        (CARRY, FLEX),            2, 0, 4),  # melee, needs HP to walk in
    _p("VESPER_VALE",     (CARRY, FLEX),            3, 0, 2, dash=True),
)}

# Used if the draft tag is missing or unreadable.
DEFAULT_PROFILE = _p("UNKNOWN", (FLEX, SUPPORT), 1, 0, 1)


def identify(raw):
    """Return the Profile whose name starts the draft-memory bytes."""
    raw = bytes(raw).rstrip(b"\0")
    for name in sorted(PROFILES, key=len, reverse=True):
        if raw.startswith(name.encode()):
            return PROFILES[name]
    return DEFAULT_PROFILE


def claim_role(profile):
    """Take the first preferred role that still has room on the team, via shared memory.

    If every preferred role is full, fall back to the champion's first preference.
    """
    counts = bytearray(3)
    cambc.shared_memory.read(ROLE_OFFSET, counts)
    for role in profile.roles:
        i = ROLE_INDEX[role]
        if counts[i] < ROLE_CAPS[role]:
            counts[i] += 1
            cambc.shared_memory.write(ROLE_OFFSET, bytes(counts))
            return role
    return profile.roles[0]
