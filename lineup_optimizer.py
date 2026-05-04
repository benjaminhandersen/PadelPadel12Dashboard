"""
Lineup optimizer for PadelPadel12Dashboard.

Rules supported:
- 2 rounds per team match
- 3 doubles pairs per round
- Same pair may only be used once
- A player may only play once per round
- With more than 6 available players, weaker players should preferably play fewer matches
"""
from __future__ import annotations

from itertools import combinations
from typing import Iterable

import pandas as pd


def all_known_players(individual: pd.DataFrame, lineup: pd.DataFrame | None) -> pd.DataFrame:
    players = []

    if lineup is not None and not lineup.empty:
        for _, row in lineup.iterrows():
            players.append({
                "player_id": int(row["player_id"]),
                "name": row["full_name"],
            })

    if individual is not None and not individual.empty:
        p1 = individual[["our_p1_id", "our_p1_name"]].rename(
            columns={"our_p1_id": "player_id", "our_p1_name": "name"}
        )
        p2 = individual[["our_p2_id", "our_p2_name"]].rename(
            columns={"our_p2_id": "player_id", "our_p2_name": "name"}
        )
        hist = pd.concat([p1, p2], ignore_index=True).dropna()
        for _, row in hist.iterrows():
            players.append({
                "player_id": int(row["player_id"]),
                "name": row["name"],
            })

    if not players:
        return pd.DataFrame(columns=["player_id", "name"])

    return (
        pd.DataFrame(players)
        .drop_duplicates(subset=["player_id"])
        .sort_values("name")
        .reset_index(drop=True)
    )


def player_history(individual: pd.DataFrame) -> pd.DataFrame:
    if individual is None or individual.empty:
        return pd.DataFrame(columns=[
            "player_id", "name", "played", "wins", "losses", "win_pct", "games_diff", "player_score"
        ])

    p1 = individual[["our_p1_id", "our_p1_name", "won", "games_diff"]].rename(
        columns={"our_p1_id": "player_id", "our_p1_name": "name"}
    )
    p2 = individual[["our_p2_id", "our_p2_name", "won", "games_diff"]].rename(
        columns={"our_p2_id": "player_id", "our_p2_name": "name"}
    )
    per = pd.concat([p1, p2], ignore_index=True)

    stats = (
        per.groupby(["player_id", "name"])
        .agg(
            played=("won", "count"),
            wins=("won", "sum"),
            games_diff=("games_diff", "sum"),
        )
        .reset_index()
    )
    stats["losses"] = stats["played"] - stats["wins"]
    stats["win_pct"] = (stats["wins"] / stats["played"] * 100).round(1)

    # Player score is intentionally simple and explainable.
    stats["player_score"] = (
        stats["wins"] * 100
        + stats["win_pct"]
        + stats["played"] * 5
        + stats["games_diff"]
    ).round(1)

    return stats.sort_values(
        ["player_score", "wins", "games_diff"],
        ascending=[False, False, False],
    ).reset_index(drop=True)


def pair_history(individual: pd.DataFrame) -> pd.DataFrame:
    if individual is None or individual.empty:
        return pd.DataFrame(columns=[
            "pair_key", "pair", "played", "wins", "losses", "win_pct", "games_diff", "pair_score"
        ])

    df = individual.copy()
    df["pair_key"] = df.apply(
        lambda row: tuple(sorted([int(row["our_p1_id"]), int(row["our_p2_id"])])),
        axis=1,
    )
    df["pair"] = df.apply(
        lambda row: " & ".join(sorted([row["our_p1_name"], row["our_p2_name"]])),
        axis=1,
    )

    stats = (
        df.groupby(["pair_key", "pair"])
        .agg(
            played=("won", "count"),
            wins=("won", "sum"),
            games_diff=("games_diff", "sum"),
        )
        .reset_index()
    )
    stats["losses"] = stats["played"] - stats["wins"]
    stats["win_pct"] = (stats["wins"] / stats["played"] * 100).round(1)

    # Pair score prioritizes actual wins together, then win percentage, match count and game difference.
    stats["pair_score"] = (
        stats["wins"] * 100
        + stats["win_pct"]
        + stats["played"] * 10
        + stats["games_diff"]
    ).round(1)

    return stats.sort_values(
        ["pair_score", "wins", "games_diff"],
        ascending=[False, False, False],
    ).reset_index(drop=True)


def _perfect_matchings(player_ids: tuple[int, ...]) -> list[tuple[tuple[int, int], tuple[int, int], tuple[int, int]]]:
    """Return all ways to create 3 disjoint pairs from exactly 6 players."""
    if len(player_ids) != 6:
        return []

    player_ids = tuple(sorted(player_ids))
    first = player_ids[0]
    matchings = []

    for partner in player_ids[1:]:
        remaining = tuple(p for p in player_ids if p not in (first, partner))
        for p2 in combinations(remaining, 2):
            rest = tuple(p for p in remaining if p not in p2)
            p3 = tuple(rest)
            pairs = tuple(sorted([
                tuple(sorted((first, partner))),
                tuple(sorted(p2)),
                tuple(sorted(p3)),
            ]))
            matchings.append(pairs)

    return sorted(set(matchings))


def _pair_label(pair: tuple[int, int], name_lookup: dict[int, str]) -> str:
    return f"{name_lookup[pair[0]]} & {name_lookup[pair[1]]}"


def suggest_two_round_lineups(
    selected_player_ids: Iterable[int],
    players_df: pd.DataFrame,
    individual: pd.DataFrame,
    max_results: int = 10,
) -> pd.DataFrame:
    """
    Suggest 2 rounds x 3 pairs.

    For each candidate, round 1 and round 2 each contain 6 players and 3 disjoint pairs.
    The same pair cannot appear twice across the full lineup.
    With more than 6 selected players, the optimizer rewards using stronger historical players more often.
    """
    selected_player_ids = sorted({int(p) for p in selected_player_ids})
    if len(selected_player_ids) < 6:
        return pd.DataFrame()

    name_lookup = dict(zip(players_df["player_id"], players_df["name"]))
    pair_stats = pair_history(individual)
    pair_lookup = {tuple(row["pair_key"]): row.to_dict() for _, row in pair_stats.iterrows()}

    player_stats = player_history(individual)
    player_score_lookup = {
        int(row["player_id"]): float(row["player_score"])
        for _, row in player_stats.iterrows()
    }

    # Unknown players get a neutral-low score, so known strong players are preferred for extra appearances.
    default_player_score = 0.0

    candidates = []
    six_player_groups = list(combinations(selected_player_ids, 6))

    for round1_players in six_player_groups:
        round1_player_set = set(round1_players)
        round1_options = _perfect_matchings(tuple(round1_players))

        for round2_players in six_player_groups:
            round2_options = _perfect_matchings(tuple(round2_players))

            appearances: dict[int, int] = {pid: 0 for pid in selected_player_ids}
            for pid in round1_players:
                appearances[pid] += 1
            for pid in round2_players:
                appearances[pid] += 1

            # Extra appearance reward: stronger players should be the ones playing twice.
            appearance_score = sum(
                player_score_lookup.get(pid, default_player_score) * count
                for pid, count in appearances.items()
            )

            for round1 in round1_options:
                used_pairs = set(round1)
                round1_pair_score = sum(float(pair_lookup.get(pair, {}).get("pair_score", 0)) for pair in round1)

                for round2 in round2_options:
                    if used_pairs.intersection(round2):
                        continue

                    all_pairs = list(round1) + list(round2)
                    pair_score = round1_pair_score + sum(
                        float(pair_lookup.get(pair, {}).get("pair_score", 0)) for pair in round2
                    )
                    historical_wins = sum(int(pair_lookup.get(pair, {}).get("wins", 0)) for pair in all_pairs)
                    historical_matches = sum(int(pair_lookup.get(pair, {}).get("played", 0)) for pair in all_pairs)
                    games_diff = sum(int(pair_lookup.get(pair, {}).get("games_diff", 0)) for pair in all_pairs)

                    # Pair history is most important. Appearance score only breaks ties / nudges extra playtime.
                    total_score = pair_score + appearance_score * 0.05

                    bench = [pid for pid, count in appearances.items() if count == 0]
                    one_match = [pid for pid, count in appearances.items() if count == 1]
                    two_matches = [pid for pid, count in appearances.items() if count == 2]

                    candidates.append({
                        "Round 1 - Par 1": _pair_label(round1[0], name_lookup),
                        "Round 1 - Par 2": _pair_label(round1[1], name_lookup),
                        "Round 1 - Par 3": _pair_label(round1[2], name_lookup),
                        "Round 2 - Par 1": _pair_label(round2[0], name_lookup),
                        "Round 2 - Par 2": _pair_label(round2[1], name_lookup),
                        "Round 2 - Par 3": _pair_label(round2[2], name_lookup),
                        "Score": round(total_score, 1),
                        "Par-score": round(pair_score, 1),
                        "Historiske sejre": historical_wins,
                        "Historiske par-kampe": historical_matches,
                        "Games±": games_diff,
                        "Spiller 2 kampe": ", ".join(name_lookup[p] for p in two_matches),
                        "Spiller 1 kamp": ", ".join(name_lookup[p] for p in one_match),
                        "Spiller 0 kampe": ", ".join(name_lookup[p] for p in bench),
                    })

    if not candidates:
        return pd.DataFrame()

    return (
        pd.DataFrame(candidates)
        .sort_values(
            ["Score", "Historiske sejre", "Games±", "Historiske par-kampe"],
            ascending=[False, False, False, False],
        )
        .drop_duplicates()
        .head(max_results)
        .reset_index(drop=True)
    )


def selected_pair_history(
    selected_player_ids: Iterable[int],
    individual: pd.DataFrame,
) -> pd.DataFrame:
    selected_pairs = {
        tuple(sorted(pair))
        for pair in combinations(sorted({int(p) for p in selected_player_ids}), 2)
    }
    hist = pair_history(individual)
    if hist.empty:
        return hist
    return hist[hist["pair_key"].isin(selected_pairs)].copy()
