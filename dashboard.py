from __future__ import annotations

import pandas as pd
import streamlit as st
from fines_ui import render_fines
from fines_connection import require_app_login
from lineup_optimizer import all_known_players
from navigation import render_navigation
from dashboard_ui import (render_team_header, render_season_highlights, render_standings,
                          render_player_cards, render_pair_cards, render_fixture_cards)

from padel_pipeline import build_dataset, stat_best_pairs, stat_per_match
from player_stats import player_set_stats, season_coverage
from app_config import load_config, get_active_season, set_active_season, upsert_season

st.set_page_config(page_title="Holdoverblik · PadelPadel 12", page_icon="🎾", layout="wide")
fines_backend = require_app_login()
render_navigation()

# Bump when the shape or interpretation of build_dataset() changes. Streamlit
# otherwise keeps results produced by older parser code in its data cache.
DATA_CACHE_VERSION = 5


def fmt_int(value, default="—"):
    if pd.isna(value):
        return default
    return str(int(value))


def fmt_signed(value, default="—"):
    if pd.isna(value):
        return default
    return f"{int(value):+d}"


def fmt_pair(row, prefix):
    return f"{row[f'{prefix}_p1_name']} & {row[f'{prefix}_p2_name']}"


def normalize_name(value: str) -> str:
    return str(value or "").lower().replace(" ", "").replace("-", "")


def resolve_team_row(standings: pd.DataFrame, team_matches: pd.DataFrame, team_id: int, active: dict) -> pd.DataFrame:
    if standings.empty:
        return pd.DataFrame()
    row = standings[standings["participant_id"] == team_id]
    if not row.empty:
        return row
    configured_names = [active.get("team_name", ""), active.get("label", "")]
    for name in configured_names:
        needle = normalize_name(name)
        if not needle:
            continue
        row = standings[standings["team_name"].apply(lambda x: needle in normalize_name(x) or normalize_name(x) in needle)]
        if not row.empty:
            return row
    if not team_matches.empty and "opponent" in team_matches.columns:
        opponent_names = {normalize_name(x) for x in team_matches["opponent"].dropna().unique()}
        candidates = standings[~standings["team_name"].apply(lambda x: normalize_name(x) in opponent_names)]
        if len(candidates) == 1:
            return candidates
    row = standings[standings["team_name"].str.contains("PadelPadel", case=False, na=False)]
    if not row.empty:
        return row
    return pd.DataFrame()


def match_detail_table(sub: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in sub.iterrows():
        rows.append({
            "Udfald": "Vundet" if r["won"] else "Tabt",
            "Os": fmt_pair(r, "our"),
            "Modstandere": fmt_pair(r, "opp"),
            "Sæt": r["sets_str"],
            "Sæt vundet": int(r["sets_won"]),
            "Sæt tabt": int(r["sets_lost"]),
            "Partier vundet": int(r["games_won"]),
            "Partier tabt": int(r["games_lost"]),
            "Partier±": int(r["games_diff"]),
        })
    return pd.DataFrame(rows)


def player_contribution_table(sub: pd.DataFrame) -> pd.DataFrame:
    if sub.empty:
        return pd.DataFrame()
    p1 = sub[["our_p1_id", "our_p1_name", "won", "games_won", "games_lost", "games_diff"]].rename(
        columns={"our_p1_id": "player_id", "our_p1_name": "Spiller"}
    )
    p2 = sub[["our_p2_id", "our_p2_name", "won", "games_won", "games_lost", "games_diff"]].rename(
        columns={"our_p2_id": "player_id", "our_p2_name": "Spiller"}
    )
    per = pd.concat([p1, p2], ignore_index=True)
    out = per.groupby(["player_id", "Spiller"]).agg(
        Kampe=("won", "count"),
        V=("won", "sum"),
        Partier_vundet=("games_won", "sum"),
        Partier_tabt=("games_lost", "sum"),
        Partier_diff=("games_diff", "sum"),
    ).reset_index()
    out["T"] = out["Kampe"] - out["V"]
    out["Win %"] = (out["V"] / out["Kampe"] * 100).round(1)
    return out.rename(columns={
        "Partier_vundet": "Partier vundet",
        "Partier_tabt": "Partier tabt",
        "Partier_diff": "Partier±",
    })[["Spiller", "Kampe", "V", "T", "Win %", "Partier vundet", "Partier tabt", "Partier±"]]


cfg = load_config()
active_key, active = get_active_season(cfg)
seasons = cfg.get("seasons", {})

st.sidebar.header("Sæson")
labels = {k: v.get("label", k) for k, v in seasons.items()}
keys = list(labels.keys())
values = list(labels.values())
selected_label = st.sidebar.selectbox("Vælg sæson", values, index=keys.index(active_key) if active_key in keys else 0)
selected_key = keys[values.index(selected_label)]

if selected_key != active_key:
    set_active_season(selected_key)
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")
with st.sidebar.expander("Tilføj ny sæson"):
    new_label = st.text_input("Navn")
    new_team_url = st.text_input("Team link")
    new_pool_url = st.text_input("Pool link")
    if st.button("Gem ny sæson"):
        if not new_label or not new_team_url:
            st.error("Udfyld navn og team link")
        else:
            upsert_season(new_label, new_team_url, new_pool_url)
            st.cache_data.clear()
            st.rerun()

team_id = int(active.get("team_id") or 2701885)
pool_id = int(active.get("pool_id") or 11353)
season_name = active.get("label", "Padel Liga")

if st.sidebar.button("Opdater data"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.caption(f"Team ID: {team_id} · Pool ID: {pool_id}")


@st.cache_data(ttl=60 * 15)
def load_data(team_id: int, pool_id: int, cache_version: int):
    return build_dataset(team_id, pool_id)


with st.spinner("Henter data fra Rankedin..."):
    try:
        data = load_data(team_id, pool_id, DATA_CACHE_VERSION)
    except Exception as e:
        st.error(f"Fejl ved dataindlæsning: {e}")
        st.stop()

team_matches = data["team_matches"]
individual = data["individual"]
lineup = data["lineup"]
standings = data["standings"]
availability = data.get("availability", {"players": pd.DataFrame(), "matches": []})
per_match = stat_per_match(team_matches, individual)

our_row = resolve_team_row(standings, team_matches, team_id, active)
our_name = our_row["team_name"].iloc[0] if not our_row.empty else active.get("team_name", f"Team {team_id}")
our_participant_id = int(our_row["participant_id"].iloc[0]) if not our_row.empty else team_id

render_team_header(our_name, season_name, our_row.iloc[0] if not our_row.empty else None, team_matches)

with st.container(key="team-overview-tabs"):
    tab_standings, tab_players, tab_pairs, tab_matches, tab_upcoming, tab_availability, tab_fines = st.tabs(
        ["Overblik", "Spillere", "Makkerpar", "Resultater", "Kampprogram", "Tilgængelighed", "Bødekassen"]
    )

with tab_fines:
    render_fines(all_known_players(individual, lineup).to_dict('records'), store=fines_backend)

with tab_standings:
    render_season_highlights(team_matches)
    st.subheader("Puljestilling")
    if standings.empty:
        st.info("Puljestillingen kunne ikke hentes.")
    else:
        show = standings.rename(columns={
            "standing": "#", "team_name": "Hold", "match_points": "Pts", "played": "Sp",
            "wins": "V", "draws": "U", "losses": "T", "sets_diff": "Sæt±", "games_diff": "Partier±",
        })[["#", "Hold", "Pts", "Sp", "V", "U", "T", "Sæt±", "Partier±", "participant_id"]]

        def highlight_us(row):
            return ["background-color: rgba(99,153,255,0.18); font-weight: 600;"] * len(row) if row["participant_id"] == our_participant_id else [""] * len(row)

        render_standings(standings, our_participant_id)
        with st.expander("Se den fulde stilling som tabel"):
            st.dataframe(
                show.style.apply(highlight_us, axis=1).format({"Sæt±": "{:+d}", "Partier±": "{:+d}"}).hide(subset=["participant_id"], axis=1),
                use_container_width=True, hide_index=True,
            )


with tab_players:
    st.subheader("Spillerstatistik")
    st.caption("Primært baseret på individuelle kampe: hvor mange doublekampe hver spiller har spillet, vundet og tabt. Sæt og partier vises som ekstra detaljer.")

    player_stats = player_set_stats(individual)
    if player_stats.empty:
        st.info("Ingen individuelle matches i data endnu.")
    else:
        main_cols = ["Spiller", "Ind. kampe", "Match V", "Match T", "Match %"]
        detail_cols = ["Sæt vundet", "Sæt tabt", "Sæt±", "Sæt %", "Partier vundet", "Partier tabt", "Partier±"]
        render_player_cards(player_stats)
        with st.expander("Se alle spillertal og sammenlign resultater"):
            st.dataframe(player_stats[main_cols + detail_cols], use_container_width=True, hide_index=True)
            chart_df = player_stats.set_index("Spiller")[["Match V", "Match T"]]
            st.bar_chart(chart_df, horizontal=True, height=300)

    with st.expander("Datakontrol: er alle 6 individuelle kampe pr. holdkamp hentet?"):
        coverage = season_coverage(team_matches, individual)
        if coverage.empty:
            st.info("Ingen spillede holdkampe at kontrollere.")
        else:
            st.dataframe(coverage, use_container_width=True, hide_index=True)
            incomplete = coverage[~coverage["Komplet"]]
            if not incomplete.empty:
                st.warning("Nogle holdkampe har færre end 6 individuelle kampe i data. Så vil spillerstatistikken også mangle kampe.")

    if lineup is not None and not lineup.empty:
        st.subheader("Trup")
        roster = lineup.rename(columns={
            "full_name": "Navn", "ranking_pts": "Ranking pts", "rating_begin": "Rating",
            "has_license": "Licens", "role": "Rolle",
        })[["Navn", "Ranking pts", "Rating", "Licens", "Rolle"]]
        st.dataframe(roster, use_container_width=True, hide_index=True)

with tab_pairs:
    st.subheader("Bedste makkerpar")
    min_matches = st.slider("Minimum antal kampe", 1, 10, 1)
    pairs = stat_best_pairs(individual, min_matches=min_matches)
    if pairs.empty:
        st.info(f"Ingen makkerpar med mindst {min_matches} kampe endnu.")
    else:
        show = pairs.rename(columns={"pair_name": "Par", "played": "Sp", "wins": "V", "losses": "T", "win_pct": "Win %"})[["Par", "Sp", "V", "T", "Win %"]]
        render_pair_cards(pairs)
        with st.expander("Se makkerpar som tabel"):
            st.dataframe(show, use_container_width=True, hide_index=True)

with tab_matches:
    st.subheader("Kampstatistik")
    played = per_match[per_match["played"]].copy() if not per_match.empty else pd.DataFrame()
    if played.empty:
        st.info("Ingen spillede kampe i data.")
    else:
        overview = played.rename(columns={
            "round": "Runde", "datetime": "Dato", "opponent": "Modstander", "venue": "H/U",
            "our_score": "Os", "their_score": "Dem", "doubles_won": "Ind. vundet",
            "doubles_played": "Ind. spillet", "total_games_won": "Partier vundet",
            "total_games_lost": "Partier tabt", "games_diff": "Partier±",
        }).copy()
        overview["Dato"] = overview["Dato"].dt.strftime("%d/%m/%Y")
        overview["H/U"] = overview["H/U"].map({"home": "Hjemme", "away": "Ude"}).fillna(overview["H/U"])
        overview["Resultat"] = overview.apply(lambda r: f"{fmt_int(r['Os'])}–{fmt_int(r['Dem'])}", axis=1)
        render_fixture_cards(played.sort_values('datetime', ascending=False), played=True)
        with st.expander("Se alle kampresultater som tabel"):
            st.dataframe(overview[["Runde", "Dato", "Modstander", "H/U", "Resultat", "Ind. vundet", "Ind. spillet", "Partier vundet", "Partier tabt", "Partier±"]], use_container_width=True, hide_index=True)

        played["label"] = played.apply(lambda r: f"R{r['round']} · {r['datetime'].strftime('%d/%m')} · {r['opponent']}", axis=1)
        choice = st.selectbox("Vælg kamp for detaljer", played["label"].tolist())
        tm_id = played.loc[played["label"] == choice, "team_match_id"].iloc[0]
        chosen = played[played["team_match_id"] == tm_id].iloc[0]
        sub = individual[individual["team_match_id"] == tm_id].copy()

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Holdkamp", f"{fmt_int(chosen['our_score'])} – {fmt_int(chosen['their_score'])}")
        c2.metric("Udfald", "Uafgjort" if chosen["our_score"] == chosen["their_score"] else ("Vundet" if chosen["won"] else "Tabt"))
        c3.metric("Individuelle", f"{fmt_int(chosen.get('doubles_won'))} / {fmt_int(chosen.get('doubles_played'))}")
        c4.metric("Partier", f"{fmt_int(chosen.get('total_games_won'))} – {fmt_int(chosen.get('total_games_lost'))}")
        c5.metric("Partier±", fmt_signed(chosen.get("games_diff")))

        if not sub.empty:
            st.markdown("**Individuelle kampe**")
            st.dataframe(match_detail_table(sub), use_container_width=True, hide_index=True)
            st.markdown("**Spillerbidrag i valgt holdkamp**")
            st.dataframe(player_contribution_table(sub), use_container_width=True, hide_index=True)

with tab_upcoming:
    st.subheader("Kommende kampe")
    upcoming = (
        team_matches[~team_matches["played"]]
        .sort_values(["datetime", "round"])
        .reset_index(drop=True)
        .copy()
        if not team_matches.empty
        else pd.DataFrame()
    )
    if upcoming.empty:
        st.success("Ingen kommende kampe i denne sæson.")
    else:
        next_match = upcoming.iloc[0]
        days_until = (next_match["datetime"].date() - pd.Timestamp.now(tz="Europe/Copenhagen").date()).days
        if days_until == 0:
            next_text = "Næste kamp er i dag"
        elif days_until == 1:
            next_text = "Næste kamp er i morgen"
        elif days_until > 1:
            next_text = f"Næste kamp er om {days_until} dage"
        else:
            next_text = "Næste kamp afventer resultat"

        home_count = int((upcoming["venue"] == "home").sum())
        away_count = int((upcoming["venue"] == "away").sum())
        st.caption(f"{len(upcoming)} kampe tilbage · {home_count} hjemme · {away_count} ude · {next_text}")

        render_fixture_cards(upcoming)

with tab_availability:
    st.subheader("Tilgængelighed")
    matches = availability.get("matches", [])
    players_df = availability.get("players", pd.DataFrame())
    if not matches:
        st.info(availability.get("reason") or "Kunne ikke hente eller parse tilgængelighedsarket.")
    else:
        if availability.get("reason"):
            st.warning(availability["reason"])
        titles = [m["title"] for m in matches]
        selected_title = st.selectbox("Vælg kamp", titles)
        selected_match = next(m for m in matches if m["title"] == selected_title)
        st.metric("Antal der kan", selected_match["available_count"])
        table = selected_match["table"].copy()
        has_answers = bool((table["Kan spille"] == "Ja").any())
        only_available = st.checkbox("Vis kun spillere der kan spille", value=has_answers)
        if only_available:
            table = table[table["Kan spille"] == "Ja"].copy()
        st.dataframe(table, use_container_width=True, hide_index=True)
        if not players_df.empty:
            st.subheader("Samlet spilleroversigt")
            st.dataframe(players_df, use_container_width=True, hide_index=True)

st.divider()
st.caption(f"Data hentet fra rankedin.com · {len(team_matches)} holdkampe · {len(individual)} individuelle matches parsed.")
