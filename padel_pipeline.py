"""
Padel dashboard — Rankedin data pipeline
=========================================

Henter holdkampe, parser individuelle doubles-matches og beregner statistik.

Tre offentlige funktioner:
  - build_dataset()    henter + parser alt (team_matches, individual, lineup, standings)
  - stat_win_loss()    win/loss pr. spiller
  - stat_best_pairs()  bedste makkerpar
  - stat_per_match()   stats pr. holdkamp

Kør direkte for at printe alt:  python padel_pipeline.py
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
OUR_TEAM_ID = 2701885        # PadelPadel 12 -
OUR_POOL_ID = 11353          # Serie 3-B Vest
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
    """Hent JSON. Cacher lokalt under udvikling så vi ikke hamrer serveren."""
    f = CACHE / f"{cache_key}.json"
    if f.exists() and not refresh:
        return json.loads(f.read_text(encoding="utf-8"))

    r = SESSION.get(url, timeout=15)
    r.raise_for_status()
    data = r.json()
    f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    time.sleep(0.4)
    return data


# ============================================================
# Endpoints
#
# ⚠ Bekræft de TO sidste URL'er i din browsers DevTools (Network-fanen).
#    Den første er bekræftet — de andre to er kvalificerede gæt
#    baseret på Rankedins navnekonvention.
# ============================================================
def url_team_matches(team_id: int) -> str:
    return f"{BASE}/teamleague/GetTeamMatchesAsync?teamid={team_id}&language=en"

def url_team_match_details(team_match_id: int) -> str:
    # GÆT — bekræft i DevTools. Skal returnere listen med 7 individuelle matches.
    return f"{BASE}/teamleague/GetTeamMatchMatchesAsync?id={team_match_id}&language=en"

def url_team_match_lineup(team_match_id: int) -> str:
    # GÆT — bekræft i DevTools. Skal returnere trupperne med RankingTypePoints.
    return f"{BASE}/teamleague/GetTeamMatchLineupAsync?id={team_match_id}&language=en"

def url_pool_standings(pool_id: int) -> str:
    # GÆT — bekræft i DevTools. Skal returnere ScoresViewModels-listen.
    return f"{BASE}/teamleague/GetPoolStandingsAsync?poolId={pool_id}&language=en"


# ============================================================
# Parsing
# ============================================================
def parse_team_matches(raw: dict, our_team_id: int) -> pd.DataFrame:
    """Holdkampe set fra vores perspektiv."""
    rows = []
    for m in raw["Matches"]:
        t1, t2 = m["Team1"], m["Team2"]
        we_are_t1 = t1["Id"] == our_team_id
        us = t1 if we_are_t1 else t2
        them = t2 if we_are_t1 else t1

        rows.append({
            "team_match_id":     m["MatchId"],
            "round":             m["Details"]["Round"],
            "datetime":          pd.to_datetime(m["Details"]["Time"],
                                                format="%d/%m/%Y %H:%M"),
            "venue":             "home" if we_are_t1 else "away",
            "location":          m["Details"].get("LocationName", ""),
            "opponent":          them["Name"],
            "opponent_id":       them["Id"],
            "played":            m["ShowResults"],
            "our_score":         us["Result"]   if m["ShowResults"] else None,
            "their_score":       them["Result"] if m["ShowResults"] else None,
            "won":               us["IsWinner"] if m["ShowResults"] else None,
            "we_are_challenger": we_are_t1,
        })
    return pd.DataFrame(rows).sort_values("round").reset_index(drop=True)


def parse_individual_matches(raw: list, team_match_id: int,
                             we_are_challenger: bool) -> list[dict]:
    """Individuelle doubles-matches fra én holdkamp."""
    individual = raw[0]["Matches"]["Matches"]
    rows = []

    for sub in individual:
        ch, cd = sub["Challenger"], sub["Challenged"]

        # Spring "Pending" placeholders over
        if ch["Player1Id"] == 0 or cd["Player1Id"] == 0:
            continue

        result = sub["MatchResult"]
        if not result.get("HasScore"):
            continue

        score = result["Score"]
        sets_raw = score.get("DetailedScoring") or []

        if we_are_challenger:
            our_side, their_side = ch, cd
            our_sets_won   = score["FirstParticipantScore"]
            their_sets_won = score["SecondParticipantScore"]
            we_won = score["IsFirstParticipantWinner"]
            sets = [(s["FirstParticipantScore"], s["SecondParticipantScore"])
                    for s in sets_raw]
        else:
            our_side, their_side = cd, ch
            our_sets_won   = score["SecondParticipantScore"]
            their_sets_won = score["FirstParticipantScore"]
            we_won = not score["IsFirstParticipantWinner"]
            sets = [(s["SecondParticipantScore"], s["FirstParticipantScore"])
                    for s in sets_raw]

        games_won  = sum(a for a, _ in sets)
        games_lost = sum(b for _, b in sets)

        rows.append({
            "team_match_id": team_match_id,
            "match_id":      sub["Id"],
            "date":          pd.to_datetime(sub["Date"]),
            "our_p1_id":     our_side["Player1Id"],
            "our_p1_name":   our_side["Name"],
            "our_p2_id":     our_side["Player2Id"],
            "our_p2_name":   our_side["Player2Name"],
            "opp_p1_id":     their_side["Player1Id"],
            "opp_p1_name":   their_side["Name"],
            "opp_p2_id":     their_side["Player2Id"],
            "opp_p2_name":   their_side["Player2Name"],
            "sets_won":      our_sets_won,
            "sets_lost":     their_sets_won,
            "games_won":     games_won,
            "games_lost":    games_lost,
            "games_diff":    games_won - games_lost,
            "sets_detail":   sets,
            "sets_str":      ", ".join(f"{a}-{b}" for a, b in sets),
            "won":           we_won,
        })
    return rows


def parse_lineup(raw: dict, our_team_id: int) -> pd.DataFrame:
    """Trup + ranking-point, filtreret til vores hold."""
    ours = raw["FirstTeam"] if raw["FirstTeam"]["Id"] == our_team_id else raw["SecondTeam"]
    rows = []
    for p in ours["Players"]:
        points = {rt["RankingType"]: rt["Points"] for rt in p.get("RankingTypePoints", [])}
        rows.append({
            "player_id":    p["PlayerId"],
            "full_name":    f"{p['FirstName']} {p['LastName']}".strip(),
            "ranked_in_id": p["PlayerRankedinId"],
            "has_license":  p["HasLicense"],
            "rating_begin": p["RatingBegin"],
            "ranking_pts":  points.get(3, 0.0),     # ranking-type 3 = serie-rangering
            "role":         "Captain" if p["TeamParticipantType"] == 3 else "Player",
        })
    return (pd.DataFrame(rows)
              .sort_values("ranking_pts", ascending=False)
              .reset_index(drop=True))


def parse_standings(raw: dict) -> pd.DataFrame:
    """Hele puljens stilling."""
    rows = []
    for t in raw["ScoresViewModels"]:
        rows.append({
            "standing":           t["Standing"],
            "participant_id":     t["ParticipantId"],
            "team_name":          t["ParticipantName"],
            "match_points":       t["MatchPoints"],
            "played":             t["Played"],
            "wins":               t["Wins"],
            "draws":              t["Draws"],
            "losses":             t["Losses"],
            "sets_diff":          t["GamesDifference"],
            "games_diff":         t["TeamGamesDifference"],
            "points_diff":        t["PointsDifference"],
        })
    return pd.DataFrame(rows).sort_values("standing").reset_index(drop=True)


# ============================================================
# Pipeline
# ============================================================
def build_dataset(our_team_id: int = OUR_TEAM_ID,
                  pool_id: int = OUR_POOL_ID,
                  refresh: bool = False) -> dict:
    """Henter alt og returnerer en dict med DataFrames."""

    # 1) Holdkampe
    raw_tm = fetch(url_team_matches(our_team_id),
                   cache_key=f"team_matches_{our_team_id}",
                   refresh=refresh)
    team_matches = parse_team_matches(raw_tm, our_team_id)

    # 2) Detaljer + lineup for hver spillet kamp
    all_ind = []
    latest_lineup = None

    for _, row in team_matches[team_matches["played"]].iterrows():
        tm_id = int(row["team_match_id"])

        try:
            raw_det = fetch(url_team_match_details(tm_id),
                            cache_key=f"match_details_{tm_id}",
                            refresh=refresh)
            all_ind.extend(parse_individual_matches(
                raw_det, tm_id, row["we_are_challenger"]))
        except Exception as e:
            print(f"⚠ Kunne ikke hente detaljer for kamp {tm_id}: {e}")

        try:
            raw_lu = fetch(url_team_match_lineup(tm_id),
                           cache_key=f"match_lineup_{tm_id}",
                           refresh=refresh)
            latest_lineup = parse_lineup(raw_lu, our_team_id)
        except Exception:
            pass   # lineup er nice-to-have, ikke kritisk

    individual = pd.DataFrame(all_ind)

    # 3) Puljestilling
    try:
        raw_st = fetch(url_pool_standings(pool_id),
                       cache_key=f"standings_{pool_id}",
                       refresh=refresh)
        standings = parse_standings(raw_st)
    except Exception:
        standings = pd.DataFrame()

    return {
        "team_matches": team_matches,
        "individual":   individual,
        "lineup":       latest_lineup,
        "standings":    standings,
    }


# ============================================================
# Statistik
# ============================================================
def stat_win_loss(individual: pd.DataFrame,
                  lineup: pd.DataFrame | None = None) -> pd.DataFrame:
    """Win/loss pr. spiller."""
    if individual.empty:
        return pd.DataFrame()

    p1 = individual[["our_p1_id", "our_p1_name", "won"]].rename(
        columns={"our_p1_id": "player_id", "our_p1_name": "name"})
    p2 = individual[["our_p2_id", "our_p2_name", "won"]].rename(
        columns={"our_p2_id": "player_id", "our_p2_name": "name"})
    per = pd.concat([p1, p2], ignore_index=True)

    stats = (per.groupby(["player_id", "name"])["won"]
                .agg(played="count", wins="sum")
                .reset_index())
    stats["losses"]  = stats["played"] - stats["wins"]
    stats["win_pct"] = (stats["wins"] / stats["played"] * 100).round(1)

    if lineup is not None and not lineup.empty:
        stats = stats.merge(lineup[["player_id", "ranking_pts", "has_license", "role"]],
                            on="player_id", how="left")

    return stats.sort_values(["win_pct", "played"],
                             ascending=[False, False]).reset_index(drop=True)


def stat_best_pairs(individual: pd.DataFrame,
                    min_matches: int = 1) -> pd.DataFrame:
    """Makkerpar-statistik."""
    if individual.empty:
        return pd.DataFrame()

    df = individual.copy()
    df["pair_key"] = df.apply(
        lambda r: tuple(sorted([r["our_p1_id"], r["our_p2_id"]])), axis=1)
    df["pair_name"] = df.apply(
        lambda r: " & ".join(sorted([r["our_p1_name"], r["our_p2_name"]])), axis=1)

    stats = (df.groupby(["pair_key", "pair_name"])["won"]
               .agg(played="count", wins="sum")
               .reset_index())
    stats["losses"]  = stats["played"] - stats["wins"]
    stats["win_pct"] = (stats["wins"] / stats["played"] * 100).round(1)
    stats = stats[stats["played"] >= min_matches]

    return stats.sort_values(["win_pct", "played"],
                             ascending=[False, False]).reset_index(drop=True)


def stat_per_match(team_matches: pd.DataFrame,
                   individual: pd.DataFrame) -> pd.DataFrame:
    """Aggregat pr. holdkamp."""
    if individual.empty:
        return team_matches.copy()

    agg = (individual.groupby("team_match_id")
                     .agg(doubles_won=("won", "sum"),
                          doubles_played=("won", "count"),
                          total_games_won=("games_won", "sum"),
                          total_games_lost=("games_lost", "sum"))
                     .reset_index())
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
    print(tm[["round", "datetime", "opponent", "venue",
              "our_score", "their_score", "won"]].to_string(index=False))

    if not data["standings"].empty:
        print("\n" + "=" * 70)
        print("PULJESTILLING")
        print("=" * 70)
        print(data["standings"][["standing", "team_name", "match_points",
                                  "played", "wins", "losses",
                                  "sets_diff", "games_diff"]].to_string(index=False))

    print("\n" + "=" * 70)
    print("WIN/LOSS PR. SPILLER")
    print("=" * 70)
    print(stat_win_loss(data["individual"], data["lineup"]).to_string(index=False))

    print("\n" + "=" * 70)
    print("BEDSTE MAKKERPAR")
    print("=" * 70)
    print(stat_best_pairs(data["individual"]).to_string(index=False))

    if data["lineup"] is not None:
        print("\n" + "=" * 70)
        print("TRUP / RANKING-POINT")
        print("=" * 70)
        print(data["lineup"].to_string(index=False))

    print("\n" + "=" * 70)
    print("STATS PR. HOLDKAMP")
    print("=" * 70)
    per = stat_per_match(data["team_matches"], data["individual"])
    print(per[["round", "opponent", "our_score", "their_score",
               "doubles_won", "doubles_played", "games_diff"]]
          .dropna(subset=["doubles_played"]).to_string(index=False))
