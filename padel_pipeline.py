"""
Padel dashboard — Rankedin data pipeline
=========================================

Henter holdkampe, parser individuelle doubles-matches og beregner statistik.

Offentlige funktioner:
  - build_dataset()    henter + parser alt
  - stat_win_loss()    win/loss pr. spiller
  - stat_best_pairs()  bedste makkerpar
  - stat_per_match()   stats pr. holdkamp

Kør direkte for at printe alt:
    python padel_pipeline.py
"""
from __future__ import annotations

import io
import json
import logging
import os
import threading
import time
from pathlib import Path

import pandas as pd
import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv er valgfrit

log = logging.getLogger(__name__)


# ============================================================
# Konfiguration
# ============================================================
API_BASE = "https://api.rankedin.com/v1"

OUR_TEAM_ID = 2701885
OUR_POOL_ID = 11353

AVAILABILITY_SHEET_XLSX_URL = os.environ.get(
    "AVAILABILITY_SHEET_URL",
    "https://docs.google.com/spreadsheets/d/"
    "1w-k6XoE_waSmGZt82l9mVPkW2CqkQxus/export?format=xlsx",
)

CACHE = Path(__file__).parent / "cache"
CACHE.mkdir(exist_ok=True)

_local = threading.local()

_DEFAULT_HEADERS = {
    "User-Agent": "PadelDashboard/1.0 (kontakt@dinklub.dk)",
    "Accept": "application/json",
}


def _get_session() -> requests.Session:
    if not hasattr(_local, "session"):
        s = requests.Session()
        s.headers.update(_DEFAULT_HEADERS)
        _local.session = s
    return _local.session


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

    response = _get_session().get(url, timeout=15)
    log.debug("GET %s → %s", url, response.status_code)
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


def url_team_match_lineup(team_match_id: int) -> str:
    return f"{API_BASE}/teamleague/GetTeamsLineupsAsync?teamMatchId={team_match_id}&language=en"


def url_team_match_details(team_match_id: int) -> str:
    return f"{API_BASE}/teamleague/GetTeamLeagueTeamsMatchesAsync?teamMatchId={team_match_id}&language=en"


# POOL_STANDINGS_URL kan sættes som miljøvariabel for at undgå at ændre koden.
# Find URL'en via DevTools: åbn rankedin.com → din puljeside → Network-fanen →
# filtrer på "api.rankedin.com" → find kaldet der returnerer "ScoresViewModels".
POOL_STANDINGS_URL = os.environ.get("POOL_STANDINGS_URL", "")

_STANDINGS_CANDIDATES = [
    "teamleague/GetTeamLeaguePoolStandingsAsync?poolId={pool_id}&language=en",
    "teamleague/GetPoolStandingsAsync?poolId={pool_id}&language=en",
    "teamleague/GetTeamLeagueStandingsAsync?poolId={pool_id}&language=en",
]


def url_pool_standings(pool_id: int) -> str:
    if POOL_STANDINGS_URL:
        return POOL_STANDINGS_URL
    # Ingen URL konfigureret — ingen standings tilgængelig.
    raise NotImplementedError(
        "Standings-URL ikke fundet endnu.\n"
        "Sæt miljøvariablen POOL_STANDINGS_URL til den fulde API-URL, du finder i\n"
        "browser DevTools mens du kigger på puljestillingen på rankedin.com.\n"
        "Kig efter et kald til api.rankedin.com der returnerer 'ScoresViewModels'."
    )


def _probe_standings_url(pool_id: int) -> str | None:
    """
    Prøver kendte URL-kandidater i rækkefølge og returnerer den første
    der svarer med gyldig JSON indeholdende 'ScoresViewModels'.
    Gemmer den fundne URL i POOL_STANDINGS_URL så den bruges fremover.
    """
    global POOL_STANDINGS_URL  # noqa: PLW0603

    for tmpl in _STANDINGS_CANDIDATES:
        url = f"{API_BASE}/{tmpl.format(pool_id=pool_id)}"
        try:
            resp = _get_session().get(url, timeout=10)
            if resp.status_code != 200:
                continue
            data = resp.json()
            if "ScoresViewModels" in data:
                log.info("Standings-URL fundet automatisk: %s", url)
                POOL_STANDINGS_URL = url
                return url
        except Exception:
            continue
    return None


# ============================================================
# Rankedin parsing
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
# Availability parsing
# ============================================================
def _clean_cell(value) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if text == "nan":
        return ""
    return text


def _load_availability_workbook() -> pd.DataFrame:
    response = _get_session().get(AVAILABILITY_SHEET_XLSX_URL, timeout=20)
    response.raise_for_status()
    return pd.read_excel(io.BytesIO(response.content), sheet_name=0, header=None)


def parse_availability_table(df_raw: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """
    Parser den øverste del af arket til:
    1) player_overview: spillere som rækker
    2) matches: liste af kampe med hvem der kan spille
    """
    df = df_raw.copy()

    # Rækker/kolonner er baseret på det konkrete ark-layout vist i billedet
    # Spillere ligger ca. på rækker 10-19 (0-baseret i pandas efter read_excel)
    player_start = 10
    player_end = 19

    if df.shape[0] <= player_end or df.shape[1] < 4:
        raise ValueError(
            f"Availability-arket har uventet størrelse {df.shape}. "
            "Tjek om arkets layout har ændret sig (forventede mindst 20 rækker og 4 kolonner)."
        )

    players = []
    for r in range(player_start, player_end + 1):
        name = _clean_cell(df.iloc[r, 0])
        side = _clean_cell(df.iloc[r, 1])
        wanted = _clean_cell(df.iloc[r, 2])
        played = _clean_cell(df.iloc[r, 3])

        if not name:
            continue

        players.append({
            "Spiller": name,
            "Side": side,
            "Ønsket": wanted,
            "Kampe": played,
            "_row_idx": r,
        })

    player_df = pd.DataFrame(players)

    matches = []
    col = 4
    max_col = df.shape[1]

    while col < max_col:
        date_val = _clean_cell(df.iloc[7, col])
        time_val = _clean_cell(df.iloc[8, col])
        home_val = _clean_cell(df.iloc[9, col])
        away_val = _clean_cell(df.iloc[9, col + 1]) if col + 1 < max_col else ""

        if date_val or time_val or home_val or away_val:
            rows = []
            available_count = 0

            for p in players:
                r = p["_row_idx"]
                can_home = _clean_cell(df.iloc[r, col]).lower() == "x"
                can_away = _clean_cell(df.iloc[r, col + 1]).lower() == "x" if col + 1 < max_col else False
                can_play = can_home or can_away

                if can_play:
                    available_count += 1

                rows.append({
                    "Spiller": p["Spiller"],
                    "Side": p["Side"],
                    "Kan spille": "Ja" if can_play else "Nej",
                    "PP-12": "x" if can_home else "",
                    "Ude": "x" if can_away else "",
                })

            match_df = pd.DataFrame(rows)

            title_parts = [part for part in [date_val, time_val, home_val, away_val] if part]
            title = " · ".join(title_parts) if title_parts else f"Kamp kolonne {col}"

            matches.append({
                "title": title,
                "date": date_val,
                "time": time_val,
                "home": home_val,
                "away": away_val,
                "available_count": available_count,
                "table": match_df,
            })

        col += 2

    if not player_df.empty:
        player_df = player_df.drop(columns=["_row_idx"])

    return player_df, matches


def load_availability_data() -> dict:
    raw = _load_availability_workbook()
    players, matches = parse_availability_table(raw)
    return {
        "raw": raw,
        "players": players,
        "matches": matches,
    }


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
            log.warning("Kunne ikke hente detaljer for kamp %s: %s", tm_id, e)

        try:
            raw_lu = fetch(
                url_team_match_lineup(tm_id),
                cache_key=f"match_lineup_{tm_id}",
                refresh=refresh,
            )
            latest_lineup = parse_lineup(raw_lu, our_team_id)
        except Exception as e:
            log.warning("Kunne ikke hente lineup for kamp %s: %s", tm_id, e)

    individual = pd.DataFrame(all_ind)

    standings = pd.DataFrame()
    try:
        raw_st = fetch(
            url_pool_standings(pool_id),
            cache_key=f"standings_{pool_id}",
            refresh=refresh,
        )
        standings = parse_standings(raw_st)
    except NotImplementedError:
        standings_url = _probe_standings_url(pool_id)
        if standings_url:
            try:
                raw_st = fetch(standings_url, cache_key=f"standings_{pool_id}", refresh=refresh)
                standings = parse_standings(raw_st)
            except Exception as e:
                log.warning("Automatisk standings-probe fejlede: %s", e)
        else:
            log.info("Standings-URL ikke konfigureret — springer over.")
    except Exception as e:
        log.warning("Kunne ikke hente stilling for pulje %s: %s", pool_id, e)

    try:
        availability = load_availability_data()
    except Exception as e:
        log.warning("Kunne ikke hente availability: %s", e)
        availability = {"raw": pd.DataFrame(), "players": pd.DataFrame(), "matches": []}

    return {
        "team_matches": team_matches,
        "individual": individual,
        "lineup": latest_lineup,
        "standings": standings,
        "availability": availability,
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