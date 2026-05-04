from __future__ import annotations

import pandas as pd


def player_set_stats(individual: pd.DataFrame) -> pd.DataFrame:
    """Player statistics based on individual matches, sets and games.

    One team match normally consists of 6 individual doubles matches.
    Each row in `individual` is one individual doubles match.
    This function expands every individual match to both players on our side
    and calculates match, set and game statistics per player.
    """
    if individual is None or individual.empty:
        return pd.DataFrame()

    p1 = individual[[
        "our_p1_id", "our_p1_name", "won", "sets_won", "sets_lost",
        "games_won", "games_lost", "games_diff"
    ]].rename(columns={
        "our_p1_id": "player_id",
        "our_p1_name": "Spiller",
    })

    p2 = individual[[
        "our_p2_id", "our_p2_name", "won", "sets_won", "sets_lost",
        "games_won", "games_lost", "games_diff"
    ]].rename(columns={
        "our_p2_id": "player_id",
        "our_p2_name": "Spiller",
    })

    per_player = pd.concat([p1, p2], ignore_index=True)

    stats = (
        per_player.groupby(["player_id", "Spiller"])
        .agg(
            Individuelle_kampe=("won", "count"),
            Match_V=("won", "sum"),
            Sets_vundet=("sets_won", "sum"),
            Sets_tabt=("sets_lost", "sum"),
            Games_vundet=("games_won", "sum"),
            Games_tabt=("games_lost", "sum"),
            Games_diff=("games_diff", "sum"),
        )
        .reset_index()
    )

    stats["Match_T"] = stats["Individuelle_kampe"] - stats["Match_V"]
    stats["Sets_total"] = stats["Sets_vundet"] + stats["Sets_tabt"]
    stats["Sæt %"] = (stats["Sets_vundet"] / stats["Sets_total"] * 100).fillna(0).round(1)
    stats["Match %"] = (stats["Match_V"] / stats["Individuelle_kampe"] * 100).fillna(0).round(1)
    stats["Sæt±"] = stats["Sets_vundet"] - stats["Sets_tabt"]

    return (
        stats.rename(columns={
            "Individuelle_kampe": "Ind. kampe",
            "Match_V": "Match V",
            "Match_T": "Match T",
            "Sets_vundet": "Sæt vundet",
            "Sets_tabt": "Sæt tabt",
            "Games_vundet": "Games vundet",
            "Games_tabt": "Games tabt",
            "Games_diff": "Games±",
        })[[
            "Spiller",
            "Ind. kampe",
            "Match V",
            "Match T",
            "Match %",
            "Sæt vundet",
            "Sæt tabt",
            "Sæt±",
            "Sæt %",
            "Games vundet",
            "Games tabt",
            "Games±",
        ]]
        .sort_values(["Sæt vundet", "Sæt %", "Games±"], ascending=[False, False, False])
        .reset_index(drop=True)
    )


def season_coverage(team_matches: pd.DataFrame, individual: pd.DataFrame) -> pd.DataFrame:
    """Show whether each played team match has the expected 6 individual matches."""
    if team_matches is None or team_matches.empty:
        return pd.DataFrame()

    played = team_matches[team_matches["played"]].copy()
    if played.empty:
        return pd.DataFrame()

    if individual is None or individual.empty:
        played["Individuelle kampe"] = 0
    else:
        counts = individual.groupby("team_match_id").size().rename("Individuelle kampe")
        played = played.merge(counts, on="team_match_id", how="left")
        played["Individuelle kampe"] = played["Individuelle kampe"].fillna(0).astype(int)

    played["Forventet"] = 6
    played["Komplet"] = played["Individuelle kampe"] == 6

    return played[[
        "round", "datetime", "opponent", "our_score", "their_score",
        "Individuelle kampe", "Forventet", "Komplet"
    ]].rename(columns={
        "round": "Runde",
        "datetime": "Dato",
        "opponent": "Modstander",
        "our_score": "Os",
        "their_score": "Dem",
    }).sort_values("Runde")
