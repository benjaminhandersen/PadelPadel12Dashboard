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
import time
from pathlib import Path

import pandas as pd
import requests


# ============================================================
# Konfiguration
# ============================================================
API_BASE = "https://api.rankedin.com/v1"

OUR_TEAM_ID = 2701885
OUR_POOL_ID = 11353

# Hvor længe lokale Rankedin JSON-filer må genbruges.
# 15 min passer med Streamlit-cache og betyder at nye resultater kommer ind løbende.
RANKEDIN_CACHE_TTL_SECONDS = 60 * 15

AVAILABILITY_SHEET_XLSX_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1kRFBarOJ3L23tCSefWv8PYyQqe2qDlvJ/export?format=xlsx"
)

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
def _cache_is_fresh(cache_file: Path, ttl_seconds: int = RANKEDIN_CACHE_TTL_SECONDS) -> bool:
    if not cache_file.exists():
        return False
    age_seconds = time.time() - cache_file.stat().st_mtime
    return age_seconds < ttl_seconds


def fetch(url: str, cache_key: str, refresh: bool = False) -> dict | list:
    cache_file = CACHE / f"{cache_key}.json"

    if cache_file.exists() and not refresh and _cache_is_fresh(cache_file):
        text = cache_file.read_text(encoding="utf-8").strip()
        if not text:
            raise ValueError(f"Cache-filen er tom: {cache_file}")
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"Ugyldig JSON i cache-filen {cache_file}: {e}") from e

    response = SESSION.get(url, timeout=15)

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


def url_pool_standings(pool_id: int) -> str:
    return f"{API_BASE}/teamleague/GetTeamStandingsAsync?poolId={pool_id}&language=en"


# ============================================================
# Rankedin parsing
# ============================================================
_MISSING = object()


def _rankedin_get(mapping: dict, pascal_name: str, default=_MISSING):
    """Read a Rankedin property in either its old or current casing."""
    camel_name = pascal_name[:1].lower() + pascal_name[1:]
    if pascal_name in mapping:
        return mapping[pascal_name]
    if camel_name in mapping:
        return mapping[camel_name]
    if default is not _MISSING:
        return default
    available = ", ".join(sorted(map(str, mapping.keys())))
    raise KeyError(
        f"Rankedin-svaret mangler '{pascal_name}'/'{camel_name}'. "
        f"Tilgængelige felter: {available or '(ingen)'}"
    )


def parse_team_matches(raw: dict, our_team_id: int) -> pd.DataFrame:
    rows = []
    for m in _rankedin_get(raw, "Matches"):
        t1, t2 = _rankedin_get(m, "Team1"), _rankedin_get(m, "Team2")
        details = _rankedin_get(m, "Details")
        we_are_t1 = _rankedin_get(t1, "Id") == our_team_id
        us = t1 if we_are_t1 else t2
        them = t2 if we_are_t1 else t1
        show_results = _rankedin_get(m, "ShowResults")

        rows.append({
            "team_match_id": _rankedin_get(m, "MatchId"),
            "round": _rankedin_get(details, "Round"),
            "datetime": pd.to_datetime(
                _rankedin_get(details, "Time"),
                format="%d/%m/%Y %H:%M",
            ),
            "venue": "home" if we_are_t1 else "away",
            "location": _rankedin_get(details, "LocationName", ""),
            "opponent": _rankedin_get(them, "Name"),
            "opponent_id": _rankedin_get(them, "Id"),
            "played": show_results,
            "our_score": _rankedin_get(us, "Result") if show_results else None,
            "their_score": _rankedin_get(them, "Result") if show_results else None,
            "won": _rankedin_get(us, "IsWinner") if show_results else None,
            "we_are_challenger": we_are_t1,
        })

    return pd.DataFrame(rows).sort_values("round").reset_index(drop=True)


def parse_individual_matches(
    raw: list,
    team_match_id: int,
    we_are_challenger: bool,
) -> list[dict]:
    matches = _rankedin_get(raw[0], "Matches")
    individual = _rankedin_get(matches, "Matches")
    settings = _rankedin_get(raw[0], "Settings", {})
    standard_order = _rankedin_get(settings, "MatchOrder", None) == 1
    rows = []

    for position, sub in enumerate(individual):
        ch, cd = _rankedin_get(sub, "Challenger"), _rankedin_get(sub, "Challenged")

        if _rankedin_get(ch, "Player1Id") == 0 or _rankedin_get(cd, "Player1Id") == 0:
            continue

        result = _rankedin_get(sub, "MatchResult")
        if not _rankedin_get(result, "HasScore", False):
            continue

        score = _rankedin_get(result, "Score")
        sets_raw = _rankedin_get(score, "DetailedScoring", []) or []

        if we_are_challenger:
            our_side, their_side = ch, cd
            our_sets_won = _rankedin_get(score, "FirstParticipantScore")
            their_sets_won = _rankedin_get(score, "SecondParticipantScore")
            we_won = _rankedin_get(score, "IsFirstParticipantWinner")
            sets = [(_rankedin_get(s, "FirstParticipantScore"), _rankedin_get(s, "SecondParticipantScore")) for s in sets_raw]
        else:
            our_side, their_side = cd, ch
            our_sets_won = _rankedin_get(score, "SecondParticipantScore")
            their_sets_won = _rankedin_get(score, "FirstParticipantScore")
            we_won = not _rankedin_get(score, "IsFirstParticipantWinner")
            sets = [(_rankedin_get(s, "SecondParticipantScore"), _rankedin_get(s, "FirstParticipantScore")) for s in sets_raw]

        games_won = sum(a for a, _ in sets)
        games_lost = sum(b for _, b in sets)

        rows.append({
            "team_match_id": team_match_id,
            "match_id": _rankedin_get(sub, "Id"),
            # Team format: first three slots are round 1, next three round 2.
            # Preserve unplayed slots; a possible seventh decider has no court.
            "court": position % 3 + 1 if standard_order and position < 6 else None,
            "lineup_round": position // 3 + 1 if standard_order and position < 6 else None,
            "date": pd.to_datetime(_rankedin_get(sub, "Date")),
            "our_p1_id": _rankedin_get(our_side, "Player1Id"),
            "our_p1_name": _rankedin_get(our_side, "Name"),
            "our_p2_id": _rankedin_get(our_side, "Player2Id"),
            "our_p2_name": _rankedin_get(our_side, "Player2Name"),
            "opp_p1_id": _rankedin_get(their_side, "Player1Id"),
            "opp_p1_name": _rankedin_get(their_side, "Name"),
            "opp_p2_id": _rankedin_get(their_side, "Player2Id"),
            "opp_p2_name": _rankedin_get(their_side, "Player2Name"),
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
    first_team = _rankedin_get(raw, "FirstTeam")
    ours = first_team if _rankedin_get(first_team, "Id") == our_team_id else _rankedin_get(raw, "SecondTeam")

    rows = []
    for p in _rankedin_get(ours, "Players"):
        points = {
            _rankedin_get(rt, "RankingType"): _rankedin_get(rt, "Points")
            for rt in _rankedin_get(p, "RankingTypePoints", [])
        }
        rows.append({
            "player_id": _rankedin_get(p, "PlayerId"),
            "full_name": f"{_rankedin_get(p, 'FirstName')} {_rankedin_get(p, 'LastName')}".strip(),
            "ranked_in_id": _rankedin_get(p, "PlayerRankedinId"),
            "has_license": _rankedin_get(p, "HasLicense"),
            "rating_begin": _rankedin_get(p, "RatingBegin"),
            "ranking_pts": points.get(3, 0.0),
            "role": "Captain" if _rankedin_get(p, "TeamParticipantType") == 3 else "Player",
        })

    columns = ["player_id", "full_name", "ranked_in_id", "has_license", "rating_begin", "ranking_pts", "role"]
    return pd.DataFrame(rows, columns=columns).sort_values("ranking_pts", ascending=False).reset_index(drop=True)


def parse_standings(raw: dict) -> pd.DataFrame:
    rows = []
    for t in _rankedin_get(raw, "ScoresViewModels"):
        rows.append({
            "standing": _rankedin_get(t, "Standing"),
            "participant_id": _rankedin_get(t, "ParticipantId"),
            "team_name": _rankedin_get(t, "ParticipantName"),
            "match_points": _rankedin_get(t, "MatchPoints"),
            "played": _rankedin_get(t, "Played"),
            "wins": _rankedin_get(t, "Wins"),
            "draws": _rankedin_get(t, "Draws"),
            "losses": _rankedin_get(t, "Losses"),
            "sets_diff": _rankedin_get(t, "GamesDifference"),
            "games_diff": _rankedin_get(t, "TeamGamesDifference"),
            "points_diff": _rankedin_get(t, "PointsDifference"),
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
    response = requests.get(AVAILABILITY_SHEET_XLSX_URL, timeout=20)
    response.raise_for_status()
    return pd.read_excel(io.BytesIO(response.content), sheet_name=0, header=None)


def _availability_layout(df: pd.DataFrame) -> tuple[int, int, int, int, int]:
    """Locate the header and player rows across the season workbook variants."""
    for row_idx in range(df.shape[0]):
        if _clean_cell(df.iloc[row_idx, 0]).lower() == "spillere":
            player_start = row_idx + 2
            player_end = player_start
            while player_end < df.shape[0]:
                name = _clean_cell(df.iloc[player_end, 0])
                if not name or name.lower().startswith("antal tilmeldte"):
                    break
                player_end += 1
            return row_idx - 1, row_idx, row_idx + 1, player_start, player_end - 1
    raise ValueError("Kunne ikke finde rækken 'Spillere' i tilgængelighedsarket")


def parse_availability_table(df_raw: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    df = df_raw.copy()
    date_row, time_row, teams_row, player_start, player_end = _availability_layout(df)

    players = []
    for r in range(player_start, player_end + 1):
        name = _clean_cell(df.iloc[r, 0])
        side = _clean_cell(df.iloc[r, 1])
        wanted = _clean_cell(df.iloc[r, 2])
        played = _clean_cell(df.iloc[r, 3])

        if not name:
            continue

        players.append({"Spiller": name, "Side": side, "Ønsket": wanted, "Kampe": played, "_row_idx": r})

    player_df = pd.DataFrame(players)
    matches = []
    col = 4
    max_col = df.shape[1]

    while col < max_col:
        date_source = df.iloc[date_row, col]
        date_val = _clean_cell(date_source)
        time_val = _clean_cell(df.iloc[time_row, col])
        home_val = _clean_cell(df.iloc[teams_row, col])
        away_val = _clean_cell(df.iloc[teams_row, col + 1]) if col + 1 < max_col else ""

        if date_val or time_val or home_val or away_val:
            rows = []
            available_count = 0

            for p in players:
                r = p["_row_idx"]
                home_answer = _clean_cell(df.iloc[r, col]).lower()
                away_answer = _clean_cell(df.iloc[r, col + 1]).lower() if col + 1 < max_col else ""
                can_home = home_answer == "x"
                can_away = away_answer == "x"
                can_play = can_home or can_away
                answered_no = home_answer == "-" or away_answer == "-"
                status = "Ja" if can_play else "Nej" if answered_no else "Ikke svaret"

                if can_play:
                    available_count += 1

                rows.append({
                    "Spiller": p["Spiller"],
                    "Side": p["Side"],
                    "Kan spille": status,
                    "PP-12": "x" if can_home else "",
                    away_val if away_val else "Modstander": "x" if can_away else "",
                })

            title_parts = [part for part in [date_val, time_val, home_val, away_val] if part]
            title = " · ".join(title_parts) if title_parts else f"Kamp kolonne {col}"

            matches.append({
                "title": title,
                "date": date_val,
                "date_source": date_source,
                "time": time_val,
                "home": home_val,
                "away": away_val,
                "available_count": available_count,
                "table": pd.DataFrame(rows),
            })

        col += 2

    if not player_df.empty:
        player_df = player_df.drop(columns=["_row_idx"])

    return player_df, matches


def _availability_dates(df_raw: pd.DataFrame) -> list[pd.Timestamp]:
    """Extract the match dates used by the fixed availability-sheet layout."""
    dates = []
    current_year = pd.Timestamp.now().year
    date_row, _, _, _, _ = _availability_layout(df_raw)
    for col in range(4, df_raw.shape[1], 2):
        value = df_raw.iloc[date_row, col]
        if pd.isna(value) or str(value).strip() == "":
            continue
        if isinstance(value, (pd.Timestamp,)) or hasattr(value, "year"):
            dates.append(pd.Timestamp(value).normalize())
            continue
        try:
            dates.append(pd.to_datetime(f"{str(value).strip()}/{current_year}", format="%d/%m/%Y"))
        except (TypeError, ValueError):
            continue
    return dates


def _possible_dates(value, year: int) -> set[pd.Timestamp]:
    """Return plausible dates, including Excel's occasional day/month swap."""
    if pd.isna(value) or str(value).strip() == "":
        return set()
    if isinstance(value, pd.Timestamp) or hasattr(value, "year"):
        date = pd.Timestamp(value).normalize()
        dates = {date}
        if date.day <= 12 and date.month <= 12 and date.day != date.month:
            dates.add(pd.Timestamp(year=date.year, month=date.day, day=date.month))
        return dates
    try:
        return {pd.to_datetime(f"{str(value).strip()}/{year}", format="%d/%m/%Y")}
    except (TypeError, ValueError):
        return set()


def _time_slot_contains(slot: str, match_time) -> bool:
    import re

    hours = [int(value) for value in re.findall(r"\d+", str(slot))]
    if len(hours) < 2:
        return True
    match_minutes = match_time.hour * 60 + match_time.minute
    start_minutes = hours[0] * 60
    end_minutes = hours[1] * 60
    return start_minutes <= match_minutes < end_minutes


def _availability_for_scheduled_matches(
    possible_matches: list[dict],
    team_matches: pd.DataFrame,
    players: pd.DataFrame,
) -> list[dict]:
    """Map survey answers onto only the fixtures that Rankedin has scheduled."""
    scheduled_matches = []
    upcoming = team_matches[~team_matches["played"]].sort_values("datetime")
    for _, match in upcoming.iterrows():
        dt = pd.Timestamp(match["datetime"])
        candidate = next((
            item for item in possible_matches
            if dt.normalize() in _possible_dates(item.get("date_source", item.get("date")), dt.year)
            and _time_slot_contains(item.get("time", ""), dt)
        ), None)

        if candidate is not None:
            table = candidate["table"][["Spiller", "Side", "Kan spille"]].copy()
        else:
            table = pd.DataFrame({
                "Spiller": players["Spiller"],
                "Side": players["Side"],
                "Kan spille": "Ikke svaret",
            })

        opponent = str(match["opponent"])
        venue = "Hjemme" if match["venue"] == "home" else "Ude"
        scheduled_matches.append({
            "title": f"Runde {int(match['round'])} · {dt.strftime('%d/%m/%Y %H:%M')} · {opponent}",
            "date": dt,
            "time": dt.strftime("%H:%M"),
            "home": venue,
            "away": opponent,
            "available_count": int((table["Kan spille"] == "Ja").sum()),
            "table": table,
        })
    return scheduled_matches


def load_availability_data(team_matches: pd.DataFrame | None = None) -> dict:
    raw = _load_availability_workbook()
    players, matches = parse_availability_table(raw)
    sheet_dates = _availability_dates(raw)

    if team_matches is not None and not team_matches.empty and sheet_dates:
        season_dates = pd.to_datetime(team_matches["datetime"]).dt.normalize()
        matching_dates = sum(
            any(abs(sheet_date - season_date) <= pd.Timedelta(days=14) for season_date in season_dates)
            for sheet_date in sheet_dates
        )
        required_matches = min(2, len(season_dates))
        overlaps_season = matching_dates >= required_matches
        if not overlaps_season:
            unanswered_matches = []
            upcoming = team_matches[~team_matches["played"]].sort_values("datetime")
            for _, match in upcoming.iterrows():
                opponent = str(match["opponent"])
                table = pd.DataFrame({
                    "Spiller": players["Spiller"],
                    "Side": players["Side"],
                    "Kan spille": "Ikke svaret",
                    opponent: "",
                })
                venue = "Hjemme" if match["venue"] == "home" else "Ude"
                unanswered_matches.append({
                    "title": f"Runde {int(match['round'])} · {match['datetime'].strftime('%d/%m/%Y %H:%M')} · {opponent}",
                    "date": match["datetime"],
                    "time": match["datetime"].strftime("%H:%M"),
                    "home": venue,
                    "away": opponent,
                    "available_count": 0,
                    "table": table,
                })

            season_players = players[["Spiller", "Side"]].copy()
            season_players["Ønsket"] = ""
            season_players["Kampe"] = ""
            return {
                "raw": raw,
                "players": season_players,
                "matches": unanswered_matches,
                "reason": "Tilgængelighedsarket er ikke opdateret til den aktive sæson. Kampene vises fra Rankedin, og alle spillere står derfor som 'Ikke svaret'.",
            }

    if team_matches is not None and not team_matches.empty:
        matches = _availability_for_scheduled_matches(matches, team_matches, players)

    return {"raw": raw, "players": players, "matches": matches, "reason": ""}


# ============================================================
# Pipeline
# ============================================================
def build_dataset(
    our_team_id: int = OUR_TEAM_ID,
    pool_id: int = OUR_POOL_ID,
    refresh: bool = False,
) -> dict:
    try:
        raw_tm = fetch(url_team_matches(our_team_id), cache_key=f"team_matches_{our_team_id}", refresh=refresh)
    except Exception as e:
        raise RuntimeError(f"Kunne ikke hente holdkampe fra Rankedin. Detalje: {e}") from e

    try:
        team_matches = parse_team_matches(raw_tm, our_team_id)
    except Exception as e:
        raise RuntimeError(
            "Kunne ikke parse holdkampe fra Rankedin; svarformatet er ændret eller ugyldigt.\n"
            f"Detalje: {e}"
        ) from e

    all_ind = []
    latest_lineup = None

    for _, row in team_matches[team_matches["played"]].iterrows():
        tm_id = int(row["team_match_id"])

        try:
            raw_det = fetch(url_team_match_details(tm_id), cache_key=f"match_details_{tm_id}", refresh=refresh)
            all_ind.extend(parse_individual_matches(raw_det, tm_id, row["we_are_challenger"]))
        except Exception as e:
            print(f"ADVARSEL: Kunne ikke hente detaljer for kamp {tm_id}: {e}")

        try:
            raw_lu = fetch(url_team_match_lineup(tm_id), cache_key=f"match_lineup_{tm_id}", refresh=refresh)
            latest_lineup = parse_lineup(raw_lu, our_team_id)
        except Exception as e:
            print(f"ADVARSEL: Kunne ikke hente lineup for kamp {tm_id}: {e}")

    individual = pd.DataFrame(all_ind)

    try:
        raw_st = fetch(url_pool_standings(pool_id), cache_key=f"standings_{pool_id}", refresh=refresh)
        standings = parse_standings(raw_st)
    except Exception as e:
        print(f"ADVARSEL: Kunne ikke hente stilling for pulje {pool_id}: {e}")
        standings = pd.DataFrame()

    try:
        availability = load_availability_data(team_matches)
    except Exception as e:
        print(f"ADVARSEL: Kunne ikke hente availability: {e}")
        availability = {"raw": pd.DataFrame(), "players": pd.DataFrame(), "matches": [], "reason": str(e)}

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
def stat_win_loss(individual: pd.DataFrame, lineup: pd.DataFrame | None = None) -> pd.DataFrame:
    if individual.empty:
        return pd.DataFrame()

    p1 = individual[["our_p1_id", "our_p1_name", "won"]].rename(columns={"our_p1_id": "player_id", "our_p1_name": "name"})
    p2 = individual[["our_p2_id", "our_p2_name", "won"]].rename(columns={"our_p2_id": "player_id", "our_p2_name": "name"})
    per = pd.concat([p1, p2], ignore_index=True)

    stats = per.groupby(["player_id", "name"])["won"].agg(played="count", wins="sum").reset_index()
    stats["losses"] = stats["played"] - stats["wins"]
    stats["win_pct"] = (stats["wins"] / stats["played"] * 100).round(1)

    if lineup is not None and not lineup.empty:
        stats = stats.merge(lineup[["player_id", "ranking_pts", "has_license", "role"]], on="player_id", how="left")

    return stats.sort_values(["win_pct", "played"], ascending=[False, False]).reset_index(drop=True)


def stat_best_pairs(individual: pd.DataFrame, min_matches: int = 1) -> pd.DataFrame:
    if individual.empty:
        return pd.DataFrame()

    df = individual.copy()
    df["pair_key"] = df.apply(lambda r: tuple(sorted([r["our_p1_id"], r["our_p2_id"]])), axis=1)
    df["pair_name"] = df.apply(lambda r: " & ".join(sorted([r["our_p1_name"], r["our_p2_name"]])), axis=1)

    stats = df.groupby(["pair_key", "pair_name"])["won"].agg(played="count", wins="sum").reset_index()
    stats["losses"] = stats["played"] - stats["wins"]
    stats["win_pct"] = (stats["wins"] / stats["played"] * 100).round(1)
    stats = stats[stats["played"] >= min_matches]

    return stats.sort_values(["win_pct", "played"], ascending=[False, False]).reset_index(drop=True)


def stat_per_match(team_matches: pd.DataFrame, individual: pd.DataFrame) -> pd.DataFrame:
    if individual.empty:
        out = team_matches.copy()
        out["doubles_won"] = pd.NA
        out["doubles_played"] = pd.NA
        out["games_diff"] = pd.NA
        return out

    agg = individual.groupby("team_match_id").agg(
        doubles_won=("won", "sum"),
        doubles_played=("won", "count"),
        total_games_won=("games_won", "sum"),
        total_games_lost=("games_lost", "sum"),
    ).reset_index()
    agg["games_diff"] = agg["total_games_won"] - agg["total_games_lost"]

    return team_matches.merge(agg, on="team_match_id", how="left")


# ============================================================
# CLI
# ============================================================
if __name__ == "__main__":
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    data = build_dataset(refresh=True)
    print("=" * 70)
    print("HOLDKAMPE")
    print("=" * 70)
    tm = data["team_matches"]
    print(tm[["round", "datetime", "opponent", "venue", "our_score", "their_score", "won"]].to_string(index=False))

    if not data["standings"].empty:
        print("\n" + "=" * 70)
        print("PULJESTILLING")
        print("=" * 70)
        print(data["standings"][["standing", "team_name", "match_points", "played", "wins", "losses", "sets_diff", "games_diff"]].to_string(index=False))
