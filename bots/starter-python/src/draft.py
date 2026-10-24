import cambc
from randomness import below

CD = cambc.ChampionDraft

# Highest priority first. Champions in the same tier are equally preferred,
# and one is chosen at random when several are still available.
PRIORITY_TIERS = [
    [CD.HEART_OF_RUIN]
    [CD.CASSI_AND_ISSAC],
    [CD.VARG],
    [CD.REN],
    [CD.STELLAR, CD.TAVI],
    [CD.WILLOW, CD.VENDETTA, CD.RYTH],
    [CD.VESPER_VALE, CD.PRISM, CD.MARCELLA],  # the rest
]

# Dictionary for the champion tags, should be easily replaced with other tags we want to use
NAMES = {
    CD.RYTH: b"RYTH",
    CD.VESPER_VALE: b"VESPER_VALE",
    CD.VENDETTA: b"VENDETTA",
    CD.CASSI_AND_ISSAC: b"CASSI_AND_ISSAC",
    CD.STELLAR: b"STELLAR",
    CD.PRISM: b"PRISM",
    CD.MARCELLA: b"MARCELLA",
    CD.WILLOW: b"WILLOW",
    CD.REN: b"REN",
    CD.VARG: b"VARG",
    CD.TAVI: b"TAVI",
    CD.HEART_OF_RUIN: b"HOR"
}

def play() -> None:
    chosen = cambc.draft.current_draft(cambc.Team.ALLY)

    # Take the first tier that still has someone available.
    for tier in PRIORITY_TIERS:
        available = [pick for pick in tier if pick not in chosen]
        if available:
            break
    pick = available[below(len(available))]

    # Draft memory starts at byte zero and is copied to each champion.
    cambc.draft_memory.submit(NAMES[pick])
    cambc.draft.pick(pick)
