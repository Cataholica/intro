import struct
from typing import List, Optional, Sequence, Tuple

from randomness import below
from Champion_strats import ROLE_RULES, identify, claim_role

import cambc
from cambc import game_map

Team, Item = cambc.Team, cambc.ItemType

class Bot:
    def __init__(self) -> None:
        # Per-champion state survives between turns. Pick one stat and keep buying it.
        self.profile = None
        self.role = None
        self.rules = None
        self.bought = {"strength": 0, "focus": 0, "health": 0}
        self.gem_tiles = cambc.Bitboard()
        self.camp_layout: Optional[
            Tuple[cambc.Bitboard, List[Tuple[game_map.CampGroup, cambc.Bitboard]]]
        ] = None
        self.home = None
        self.enemy_home = None
        self.trip_start = 0
        self.trips = 0
        self.idle_turns = 0
        self.shards_bought = 0

    def reach(self):
        base = BASE_REACH + REACH_PER_TRIP * self.trips + REACH_PER_SHARD * self.shards_bought + (cambc.round_number()//10)
        bonus = DASH_REACH_BONUS if self.profile.dash else 0
        return base * self.rules.reach_scale + bonus

    def may_invade(self):
        if self.shards_bought < self.rules.invade_shards:
            return False
        threshold = max(INVADE_MIN_IDLE, INVADE_IDLE_TURNS - 2 * self.shards_bought)
        return self.idle_turns >= threshold

    def buy_items(self):
        me = cambc.me()
        gold = me.gold_count()
        allowed = None if self.rules.item_cap is None else self.rules.item_cap - self.shards_bought
        weights = self.profile.build
        weight_sum = sum(weights.values())
        plan = {stat: 0 for stat in SHARD_ITEMS}
        total = sum(self.bought.values())
        while allowed is None or allowed > 0:
            stat = max(weights, key=lambda s: weights[s] / weight_sum * (total + 1)
                       - self.bought[s] - plan[s])
            cost = SHARD_ITEMS[stat].cost()
            if cost <= 0 or gold < cost:
                break
            plan[stat] += 1
            gold -= cost
            total += 1
            if allowed is not None:
                allowed -= 1
        for stat, count in plan.items():
            if count and me.can_buy(SHARD_ITEMS[stat], count):
                me.buy(SHARD_ITEMS[stat], count)
                self.bought[stat] += count
                self.shards_bought += count

    def play_turn(self) -> None:
        # Initialise this champion's build and read the draft message once.
        if self.profile is None:
            self.profile = identify(cambc.DraftMemoryBuffer())
            self.role = claim_role(self.profile)
            self.rules = ROLE_RULES[self.role]
            self.home = game_map.spawn_region(Team.ALLY).positions()[0]
            self.enemy_home = game_map.spawn_region(Team.ENEMY).positions()[0]
            print("champion:", self.profile.name, "role:", self.role)

        # Read before writing: little-endian u32 at shared-memory byte offset zero.
        data = bytearray(4)
        cambc.shared_memory.read(0, data)
        print("shared round:", struct.unpack("<I", data)[0])
        cambc.shared_memory.write(0, struct.pack("<I", cambc.round_number()))

        # Priorities: shop and recall, attack enemies in range, bank gems, then farm.
        me = cambc.me()

        # Leave channels running and skip turns where we cannot act.
        if (not me.is_alive() or me.is_recalling() or me.is_submitting_gems() or me.is_teleporting()
                or (not me.can_move() and not me.can_attack())):
            return

        # Shop before leaving spawn.
        at_spawn = game_map.spawn_region(Team.ALLY).is_set(me.position())
        if at_spawn:
            self.trip_start = cambc.round_number()
            self.buy_items()

        # Recall immediately when badly hurt away from spawn.
        if not at_spawn and me.health() < me.max_health() * 0.35:
            me.recall()
            return
"""
Alternative recall strat
Timed recall: hard floor early in a trip, softer inside the respawn window.
        if not at_spawn:
            trip_turns = cambc.round_number() - self.trip_start
            if me.health() < me.max_health() * recall_threshold(trip_turns):
            self.trips += 1
            self.idle_turns = 0
            me.recall()
                return
"""
        
        # Attack the first enemy champion already in range.
        if attack_first_in_range(weakest_first(cambc.vision.champions(Team.ENEMY))):
            return

        # Bank any carried gems before farming.
        if me.gem_count() > 0:
            # Union all altar approach tiles: the field chooses the nearest reachable altar.
            goals = cambc.Bitboard()
            for altar in game_map.altars().positions():
                if cambc.vision.has_altar_lock(altar):
                    continue
                if distance(me.position(), altar) <= cambc.constants.SUBMIT_GEMS_RANGE:
                    me.submit_gems(altar)
                    return
                goals |= tiles_around(altar, cambc.constants.SUBMIT_GEMS_RANGE)
            if move_towards_closest(goals):
                return

        farm_camps(self)

        me.set_priority(1 + below(100))
