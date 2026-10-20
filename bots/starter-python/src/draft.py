import cambc
from randomness import below


def play() -> None:
    # We will eventually work towards a draft system that essentially emphasises the S-tire units first
    # then work down the tierlist once all the high-tier champions are chosen
    chosen = cambc.draft.current_draft(cambc.Team.ALLY)
    available = [
        pick for pick in (
            cambc.ChampionDraft.RYTH,
            cambc.ChampionDraft.VESPER_VALE,
            cambc.ChampionDraft.VENDETTA,
            cambc.ChampionDraft.CASSI_AND_ISSAC,
            cambc.ChampionDraft.STELLAR,
            cambc.ChampionDraft.PRISM,
            cambc.ChampionDraft.MARCELLA,
            cambc.ChampionDraft.WILLOW,
            cambc.ChampionDraft.REN,
            cambc.ChampionDraft.VARG,
            cambc.ChampionDraft.TAVI,
        ) if pick not in chosen
    ]

    # Draft memory starts at byte zero and is copied to each champion.
    cambc.draft_memory.submit(b"hello world")
    cambc.draft.pick(available[below(len(available))])
