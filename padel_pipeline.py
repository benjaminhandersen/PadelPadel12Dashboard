"""
Padel dashboard — Rankedin data pipeline
=========================================

Henter holdkampe, parser individuelle doubles-matches og beregner statistik.

Offentlige funktioner:
  - build_dataset()    henter + parser alt (team_matches, individual, lineup, standings)
  - stat_win_loss()    win/loss pr. spiller
  - stat_best_pairs()  bedste makkerpar
  - stat_per_match()   stats pr. holdkamp

Kør direkte for at printe alt:
    python padel_pipeline.py
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd
import requests


# ============================================================
# Konfiguration
# ============================================================
BASE = "https://rankedin.com"
API_BASE = "https://api.rankedin.com/v1"

OUR_TEAM_ID = 2701885
OUR_POOL_ID = 11353

CACHE = Path(__file__).parent / "cache"
CACHE.mkdir(exist_ok=True)

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "PadelDashboard/1.0 (kontakt@dinklub.dk)",
    "Accept": "application/json",
})


# ============================================================
# HTTP med lokal cache
# ============================================================
def fetch(url: str, cache_key: str, refresh: bool = False) -> dict | list:
    cache_file = CACHE / f"{cache_key}.json"

    if cache_file.exists() and not refresh:
        text = cache_file.read_text(encoding="utf-8").strip()
        if not text:
            raise ValueError(f"Cache-filen er tom: {cache_file}")
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"Ugyldig JSON i cache-filen {cache_file}: {e}") from e

    response = SESSION.get(url, timeout=15)

    print("\n--- DEBUG FETCH ---")
    print("URL:", url)
    print("Status:", response.status_code)
    print("Content-Type:", response.headers.get("Content-Type"))
    print("Første 500 tegn af svar:")
    print(response.text[:500])
    print("--- END DEBUG ---\n")

    response.raise_for_status()

    text = response.text.strip()
    if not text:
        raise ValueError(f"Tomt svar fra URL: {url}")

    try:
        data = response.json()
    except Exception as e:
        raise ValueError(
            f"Svaret er ikke gyldig JSON.\n"
            f"URL: {url}\n"
            f"Status: {response.status_code}\n"
            f"Content-Type: {response.headers.get('Content-Type')}\n"
            f"Første 500 tegn:\n{text[:500]}"
        ) from e

    cache_file.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    time.sleep(0.4)
    return data


# ============================================================
# Endpoints
# ============================================================
def url_team_matches(team_id: int) -> str:
    return f"{API_BASE}/teamleague/GetTeamMatchesAsync?teamid={team_id}&language=en"


def url_team_match_result_model(team_match_id: int) -> str:
    return f"{API_BASE}/teamleague/GetTeamMatchResultModelAsync?matchId={team_match_id}"


def url_team_match_lineup(team_match_id: int) -> str:
    return f"{API_BASE}/teamleague/GetTeamsLineupsAsync?teamMatchId={team_match_id}&language=en"


def url_team_match_summary(team_match_id: int) -> str:
    return f"{API_BASE}/teamleague/TeamLeagueTeamMatchStandingsAsync?teamMatchId={team_match_id}&language=en"


def url_team_match_details(team_match_id: int) -> str:
    return f"{API_BASE}/teamleague/GetTeamLeagueTeamsMatchesAsync?teamMatchId={team_match_id}&language=en"


def url_pool_standings(pool_id: int) -> str:
    raise NotImplementedError(
        "Find Request URL i DevTools for standings-endpointet med ScoresViewModels."
    )

# ============================================================
# Parsing
# ============================================================
def parse_team_matches(raw: dict, our_team_id: int) -> pd.DataFrame:
    rows = []
    for m in raw["Matches"]:
        t1, t2 = m["Team1"], m["Team2"]
        we_are_t1 = t1["Id"] == our_team_id
        us = t1 if we_are_t1 else t2
        them = t2 if we_are_t1 else t1

        rows.append({
            "team_match_id": m["MatchId"],
            "round": m["Details"]["Round"],
            "datetime": pd.to_datetime(
                m["Details"]["Time"],
                format="%d/%m/%Y %H:%M",
            ),
            "venue": "home" if we_are_t1 else "away",
            "location": m["Details"].get("LocationName", ""),
            "opponent": them["Name"],
            "opponent_id": them["Id"],
            "played": m["ShowResults"],
            "our_score": us["Result"] if m["ShowResults"] else None,
            "their_score": them["Result"] if m["ShowResults"] else None,
            "won": us["IsWinner"] if m["ShowResults"] else None,
            "we_are_challenger": we_are_t1,
        })

    return pd.DataFrame(rows).sort_values("round").reset_index(drop=True)


def parse_individual_matches(
    raw: list,
    team_match_id: int,
    we_are_challenger: bool,
) -> list[dict]:
    individual = raw[0]["Matches"]["Matches"]
    rows = []

    for sub in individual:
        ch, cd = sub["Challenger"], sub["Challenged"]

        if ch["Player1Id"] == 0 or cd["Player1Id"] == 0:
            continue

        result = sub["MatchResult"]
        if not result.get("HasScore"):
            continue

        score = result["Score"]
        sets_raw = score.get("DetailedScoring") or []

        if we_are_challenger:
            our_side, their_side = ch, cd
            our_sets_won = score["FirstParticipantScore"]
            their_sets_won = score["SecondParticipantScore"]
            we_won = score["IsFirstParticipantWinner"]
            sets = [
                (s["FirstParticipantScore"], s["SecondParticipantScore"])
                for s in sets_raw
            ]
        else:
            our_side, their_side = cd, ch
            our_sets_won = score["SecondParticipantScore"]
            their_sets_won = score["FirstParticipantScore"]
            we_won = not score["IsFirstParticipantWinner"]
            sets = [
                (s["SecondParticipantScore"], s["FirstParticipantScore"])
                for s in sets_raw
            ]

        games_won = sum(a for a, _ in sets)
        games_lost = sum(b for _, b in sets)

        rows.append({
            "team_match_id": team_match_id,
            "match_id": sub["Id"],
            "date": pd.to_datetime(sub["Date"]),
            "our_p1_id": our_side["Player1Id"],
            "our_p1_name": our_side["Name"],
            "our_p2_id": our_side["Player2Id"],
            "our_p2_name": our_side["Player2Name"],
            "opp_p1_id": their_side["Player1Id"],
            "opp_p1_name": their_side["Name"],
            "opp_p2_id": their_side["Player2Id"],
            "opp_p2_name": their_side["Player2Name"],
            "sets_won": our_sets_won,
            "sets_lost": their_sets_won,
            "games_won": games_won,
            "games_lost": games_lost,
            "games_diff": games_won - games_lost,
            "sets_detail": sets,
            "sets_str": ", ".join(f"{a}-{b}" for a, b in sets),
            "won": we_won,
        })

    return rows


def parse_lineup(raw: dict, our_team_id: int) -> pd.DataFrame:
    ours = raw["FirstTeam"] if raw["FirstTeam"]["Id"] == our_team_id else raw["SecondTeam"]

    rows = []
    for p in ours["Players"]:
        points = {
            rt["RankingType"]: rt["Points"]
            for rt in p.get("RankingTypePoints", [])
        }
        rows.append({
            "player_id": p["PlayerId"],
            "full_name": f"{p['FirstName']} {p['LastName']}".strip(),
            "ranked_in_id": p["PlayerRankedinId"],
            "has_license": p["HasLicense"],
            "rating_begin": p["RatingBegin"],
            "ranking_pts": points.get(3, 0.0),
            "role": "Captain" if p["TeamParticipantType"] == 3 else "Player",
        })

    return (
        pd.DataFrame(rows)
        .sort_values("ranking_pts", ascending=False)
        .reset_index(drop=True)
    )


def parse_standings(raw: dict) -> pd.DataFrame:
    rows = []
    for t in raw["ScoresViewModels"]:
        rows.append({
            "standing": t["Standing"],
            "participant_id": t["ParticipantId"],
            "team_name": t["ParticipantName"],
            "match_points": t["MatchPoints"],
            "played": t["Played"],
            "wins": t["Wins"],
            "draws": t["Draws"],
            "losses": t["Losses"],
            "sets_diff": t["GamesDifference"],
            "games_diff": t["TeamGamesDifference"],
            "points_diff": t["PointsDifference"],
        })

    return pd.DataFrame(rows).sort_values("standing").reset_index(drop=True)


# ============================================================
# Pipeline
# ============================================================
def build_dataset(
    our_team_id: int = OUR_TEAM_ID,
    pool_id: int = OUR_POOL_ID,
    refresh: bool = False,
) -> dict:
    try:
        raw_tm = fetch(
            url_team_matches(our_team_id),
            cache_key=f"team_matches_{our_team_id}",
            refresh=refresh,
        )
        team_matches = parse_team_matches(raw_tm, our_team_id)
    except Exception as e:
        raise RuntimeError(
            "Kunne ikke hente holdkampe fra Rankedin.\n"
            "URL'en i url_team_matches() matcher sandsynligvis ikke den rigtige request.\n"
            f"Detalje: {e}"
        ) from e

    all_ind = []
    latest_lineup = None

    for _, row in team_matches[team_matches["played"]].iterrows():
        tm_id = int(row["team_match_id"])

        try:
            raw_det = fetch(
                url_team_match_details(tm_id),
                cache_key=f"match_details_{tm_id}",
                refresh=refresh,
            )
            all_ind.extend(
                parse_individual_matches(
                    raw_det,
                    tm_id,
                    row["we_are_challenger"],
                )
            )
        except Exception as e:
            print(f"⚠ Kunne ikke hente detaljer for kamp {tm_id}: {e}")

        try:
            raw_lu = fetch(
                url_team_match_lineup(tm_id),
                cache_key=f"match_lineup_{tm_id}",
                refresh=refresh,
            )
            latest_lineup = parse_lineup(raw_lu, our_team_id)
        except Exception as e:
            print(f"⚠ Kunne ikke hente lineup for kamp {tm_id}: {e}")

    individual = pd.DataFrame(all_ind)

    try:
        raw_st = fetch(
            url_pool_standings(pool_id),
            cache_key=f"standings_{pool_id}",
            refresh=refresh,
        )
        standings = parse_standings(raw_st)
    except Exception as e:
        print(f"⚠ Kunne ikke hente stilling for pulje {pool_id}: {e}")
        standings = pd.DataFrame()

    return {
        "team_matches": team_matches,
        "individual": individual,
        "lineup": latest_lineup,
        "standings": standings,
    }


# ============================================================
# Statistik
# ============================================================
def stat_win_loss(
    individual: pd.DataFrame,
    lineup: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if individual.empty:
        return pd.DataFrame()

    p1 = individual[["our_p1_id", "our_p1_name", "won"]].rename(
        columns={"our_p1_id": "player_id", "our_p1_name": "name"}
    )
    p2 = individual[["our_p2_id", "our_p2_name", "won"]].rename(
        columns={"our_p2_id": "player_id", "our_p2_name": "name"}
    )
    per = pd.concat([p1, p2], ignore_index=True)

    stats = (
        per.groupby(["player_id", "name"])["won"]
        .agg(played="count", wins="sum")
        .reset_index()
    )
    stats["losses"] = stats["played"] - stats["wins"]
    stats["win_pct"] = (stats["wins"] / stats["played"] * 100).round(1)

    if lineup is not None and not lineup.empty:
        stats = stats.merge(
            lineup[["player_id", "ranking_pts", "has_license", "role"]],
            on="player_id",
            how="left",
        )

    return stats.sort_values(
        ["win_pct", "played"],
        ascending=[False, False],
    ).reset_index(drop=True)


def stat_best_pairs(
    individual: pd.DataFrame,
    min_matches: int = 1,
) -> pd.DataFrame:
    if individual.empty:
        return pd.DataFrame()

    df = individual.copy()
    df["pair_key"] = df.apply(
        lambda r: tuple(sorted([r["our_p1_id"], r["our_p2_id"]])),
        axis=1,
    )
    df["pair_name"] = df.apply(
        lambda r: " & ".join(sorted([r["our_p1_name"], r["our_p2_name"]])),
        axis=1,
    )

    stats = (
        df.groupby(["pair_key", "pair_name"])["won"]
        .agg(played="count", wins="sum")
        .reset_index()
    )
    stats["losses"] = stats["played"] - stats["wins"]
    stats["win_pct"] = (stats["wins"] / stats["played"] * 100).round(1)
    stats = stats[stats["played"] >= min_matches]

    return stats.sort_values(
        ["win_pct", "played"],
        ascending=[False, False],
    ).reset_index(drop=True)


def stat_per_match(
    team_matches: pd.DataFrame,
    individual: pd.DataFrame,
) -> pd.DataFrame:
    if individual.empty:
        out = team_matches.copy()
        out["doubles_won"] = pd.NA
        out["doubles_played"] = pd.NA
        out["games_diff"] = pd.NA
        return out

    agg = (
        individual.groupby("team_match_id")
        .agg(
            doubles_won=("won", "sum"),
            doubles_played=("won", "count"),
            total_games_won=("games_won", "sum"),
            total_games_lost=("games_lost", "sum"),
        )
        .reset_index()
    )
    agg["games_diff"] = agg["total_games_won"] - agg["total_games_lost"]

    return team_matches.merge(agg, on="team_match_id", how="left")


# ============================================================
# CLI
# ============================================================
if __name__ == "__main__":
    data = build_dataset()

    print("=" * 70)
    print("HOLDKAMPE")
    print("=" * 70)
    tm = data["team_matches"]
    print(
        tm[[
            "round",
            "datetime",
            "opponent",
            "venue",
            "our_score",
            "their_score",
            "won",
        ]].to_string(index=False)
    )

    if not data["standings"].empty:
        print("\n" + "=" * 70)
        print("PULJESTILLING")
        print("=" * 70)
        print(
            data["standings"][[
                "standing",
                "team_name",
                "match_points",
                "played",
                "wins",
                "losses",
                "sets_diff",
                "games_diff",
            ]].to_string(index=False)
        )

    print("\n" + "=" * 70)
    print("WIN/LOSS PR. SPILLER")
    print("=" * 70)
    wl = stat_win_loss(data["individual"], data["lineup"])
    if wl.empty:
        print("Ingen individuelle kampdata hentet endnu.")
    else:
        print(wl.to_string(index=False))

    print("\n" + "=" * 70)
    print("BEDSTE MAKKERPAR")
    print("=" * 70)
    bp = stat_best_pairs(data["individual"])
    if bp.empty:
        print("Ingen individuelle kampdata hentet endnu.")
    else:
        print(bp.to_string(index=False))

    if data["lineup"] is not None and not data["lineup"].empty:
        print("\n" + "=" * 70)
        print("TRUP / RANKING-POINT")
        print("=" * 70)
        print(data["lineup"].to_string(index=False))

    print("\n" + "=" * 70)
    print("STATS PR. HOLDKAMP")
    print("=" * 70)
    per = stat_per_match(data["team_matches"], data["individual"])
    cols = [
        "round",
        "opponent",
        "our_score",
        "their_score",
        "doubles_won",
        "doubles_played",
        "games_diff",
    ]
    vis = per[cols].dropna(subset=["doubles_played"])
    if vis.empty:
        print("Ingen individuelle kampdata hentet endnu.")
    else:
        print(vis.to_string(index=False))