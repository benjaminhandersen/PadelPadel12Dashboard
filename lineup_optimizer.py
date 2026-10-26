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


# Heuristic strength index, not a win probability. Two neutral prior matches
# limit the effect of tiny samples. Court is inferred by the parser from slots.
NEUTRAL_SCORE = 50.0


def _scored_matches(individual: pd.DataFrame) -> pd.DataFrame:
    df = individual.copy()
    courts = df.get("court", pd.Series(index=df.index, dtype=float))
    bonus = courts.map({1: 20.0, 2: 0.0, 3: -20.0}).fillna(0.0)
    df["performance"] = (df["won"].astype(float) * 100
                         + df["games_diff"].clip(-10, 10) + bonus)
    return df


def player_history(individual: pd.DataFrame) -> pd.DataFrame:
    columns = ["player_id", "name", "played", "wins", "losses", "win_pct", "games_diff", "player_score"]
    if individual is None or individual.empty:
        return pd.DataFrame(columns=columns)
    df = _scored_matches(individual)
    parts = [df[[f"our_p{i}_id", f"our_p{i}_name", "won", "games_diff", "performance"]]
             .rename(columns={f"our_p{i}_id": "player_id", f"our_p{i}_name": "name"})
             for i in (1, 2)]
    stats = (pd.concat(parts, ignore_index=True).groupby(["player_id", "name"])
             .agg(played=("won", "count"), wins=("won", "sum"),
                  games_diff=("games_diff", "sum"), performance=("performance", "sum"))
             .reset_index())
    stats["losses"] = stats["played"] - stats["wins"]
    stats["win_pct"] = (stats["wins"] / stats["played"] * 100).round(1)
    stats["player_score"] = ((stats["performance"] + 2 * NEUTRAL_SCORE)
                             / (stats["played"] + 2)).round(2)
    return stats.drop(columns="performance").sort_values("player_score", ascending=False).reset_index(drop=True)


def pair_history(individual: pd.DataFrame) -> pd.DataFrame:
    columns = ["pair_key", "pair", "played", "wins", "losses", "win_pct", "games_diff", "pair_score"]
    if individual is None or individual.empty:
        return pd.DataFrame(columns=columns)
    df = _scored_matches(individual)
    df["pair_key"] = df.apply(lambda r: tuple(sorted([int(r["our_p1_id"]), int(r["our_p2_id"])])), axis=1)
    df["pair"] = df.apply(lambda r: " & ".join(sorted([r["our_p1_name"], r["our_p2_name"]])), axis=1)
    stats = (df.groupby(["pair_key", "pair"])
             .agg(played=("won", "count"), wins=("won", "sum"),
                  games_diff=("games_diff", "sum"), performance=("performance", "sum"))
             .reset_index())
    scores = player_history(individual).set_index("player_id")["player_score"].to_dict()
    baseline = stats["pair_key"].map(lambda pair: sum(scores.get(p, NEUTRAL_SCORE) for p in pair) / 2)
    # Four equivalent matches from individuals: zero shared games uses only
    # individuals; four shared games gives shared performance half the weight.
    stats["pair_score"] = ((stats["performance"] + 4 * baseline) / (stats["played"] + 4)).round(2)
    stats["losses"] = stats["played"] - stats["wins"]
    stats["win_pct"] = (stats["wins"] / stats["played"] * 100).round(1)
    for court in (1, 2, 3):
        on_court = df[df.get("court", pd.Series(index=df.index, dtype=float)) == court]
        counts = on_court.groupby("pair_key")["won"].agg(["count", "sum"])
        stats[f"court_{court}_played"] = stats["pair_key"].map(counts["count"]).fillna(0).astype(int)
        stats[f"court_{court}_wins"] = stats["pair_key"].map(counts["sum"]).fillna(0).astype(int)
    return stats.drop(columns="performance").sort_values("pair_score", ascending=False).reset_index(drop=True)


def pair_strengths(selected_player_ids, individual):
    """Same strength scale for established pairs and individual-only estimates."""
    players = player_history(individual)
    scores = players.set_index("player_id")["player_score"].to_dict()
    history = pair_history(individual)
    known = {tuple(r["pair_key"]): float(r["pair_score"]) for _, r in history.iterrows()}
    return {pair: known.get(pair, sum(scores.get(p, NEUTRAL_SCORE) for p in pair) / 2)
            for pair in combinations(sorted(set(selected_player_ids)), 2)}


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

    # Players without any history use a neutral prior.
    default_player_score = NEUTRAL_SCORE
    strength_lookup = pair_strengths(selected_player_ids, individual)

    candidates = []
    six_player_groups = list(combinations(selected_player_ids, 6))

    for round1_players in six_player_groups:
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
                round1_pair_score = sum(strength_lookup[pair] for pair in round1)

                for round2 in round2_options:
                    if used_pairs.intersection(round2):
                        continue

                    all_pairs = list(round1) + list(round2)
                    pair_score = round1_pair_score + sum(
                        strength_lookup[pair] for pair in round2
                    )
                    historical_wins = sum(int(pair_lookup.get(pair, {}).get("wins", 0)) for pair in all_pairs)
                    historical_matches = sum(int(pair_lookup.get(pair, {}).get("played", 0)) for pair in all_pairs)
                    games_diff = sum(int(pair_lookup.get(pair, {}).get("games_diff", 0)) for pair in all_pairs)

                    # Estimated pair strength dominates; individual scores nudge extra playtime.
                    total_score = pair_score + appearance_score * 0.05

                    bench = [pid for pid, count in appearances.items() if count == 0]
                    one_match = [pid for pid, count in appearances.items() if count == 1]
                    two_matches = [pid for pid, count in appearances.items() if count == 2]

                    ordered1 = sorted(round1, key=lambda pair: (-strength_lookup[pair], pair))
                    ordered2 = sorted(round2, key=lambda pair: (-strength_lookup[pair], pair))
                    candidates.append({
                        "Round 1 - Par 1": _pair_label(ordered1[0], name_lookup),
                        "Round 1 - Par 2": _pair_label(ordered1[1], name_lookup),
                        "Round 1 - Par 3": _pair_label(ordered1[2], name_lookup),
                        "Round 2 - Par 1": _pair_label(ordered2[0], name_lookup),
                        "Round 2 - Par 2": _pair_label(ordered2[1], name_lookup),
                        "Round 2 - Par 3": _pair_label(ordered2[2], name_lookup),
                        **{f"Round {r} - Par {i+1} score": round(strength_lookup[pair], 2)
                           for r, pairs in ((1, ordered1), (2, ordered2)) for i, pair in enumerate(pairs)},
                        "Score": round(total_score, 2),
                        "Par-score": round(pair_score, 1),
                        "Historiske sejre": historical_wins,
                        "Historiske par-kampe": historical_matches,
                        "Partier±": games_diff,
                        "Spiller 2 kampe": ", ".join(name_lookup[p] for p in two_matches),
                        "Spiller 1 kamp": ", ".join(name_lookup[p] for p in one_match),
                        "Spiller 0 kampe": ", ".join(name_lookup[p] for p in bench),
                    })

    if not candidates:
        return pd.DataFrame()

    return (
        pd.DataFrame(candidates)
        .sort_values(
            ["Score", "Historiske sejre", "Partier±", "Historiske par-kampe"],
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
