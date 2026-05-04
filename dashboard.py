from __future__ import annotations

import pandas as pd
import streamlit as st

from padel_pipeline import build_dataset, stat_best_pairs, stat_per_match
from player_stats import player_set_stats, season_coverage
from app_config import load_config, get_active_season, set_active_season, upsert_season

st.set_page_config(page_title="Padel Dashboard", page_icon="🎾", layout="wide")


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
            "Games vundet": int(r["games_won"]),
            "Games tabt": int(r["games_lost"]),
            "Games±": int(r["games_diff"]),
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
        Games_vundet=("games_won", "sum"),
        Games_tabt=("games_lost", "sum"),
        Games_diff=("games_diff", "sum"),
    ).reset_index()
    out["T"] = out["Kampe"] - out["V"]
    out["Win %"] = (out["V"] / out["Kampe"] * 100).round(1)
    return out.rename(columns={
        "Games_vundet": "Games vundet",
        "Games_tabt": "Games tabt",
        "Games_diff": "Games±",
    })[["Spiller", "Kampe", "V", "T", "Win %", "Games vundet", "Games tabt", "Games±"]]


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
st.sidebar.subheader("Tilføj ny sæson")
new_label = st.sidebar.text_input("Navn")
new_team_url = st.sidebar.text_input("Team link")
new_pool_url = st.sidebar.text_input("Pool link")
if st.sidebar.button("Gem ny sæson"):
    if not new_label or not new_team_url:
        st.sidebar.error("Udfyld navn og team link")
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
def load_data(team_id: int, pool_id: int):
    return build_dataset(team_id, pool_id)


with st.spinner("Henter data fra Rankedin..."):
    try:
        data = load_data(team_id, pool_id)
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

st.title(our_name)
st.caption(f"{season_name} · kilde: rankedin.com")

col1, col2, col3, col4 = st.columns(4)
if not our_row.empty:
    s = our_row.iloc[0]
    total_matches = int(standings["played"].max()) if "played" in standings.columns and not standings.empty else len(team_matches)
    col1.metric("Placering", f"{s['standing']} / {len(standings)}")
    col2.metric("Kampe", f"{s['played']} / {total_matches}")
    col3.metric("Vundet / tabt", f"{s['wins']} / {s['losses']}")
    col4.metric("Games-diff", f"{int(s['games_diff']):+d}")
else:
    played_count = int(team_matches["played"].sum()) if not team_matches.empty else 0
    won_count = int(team_matches["won"].fillna(False).sum()) if not team_matches.empty else 0
    col1.metric("Placering", "—")
    col2.metric("Kampe", f"{played_count} / {len(team_matches)}")
    col3.metric("Vundet / tabt", f"{won_count} / {played_count - won_count}")
    col4.metric("Games-diff", "—")

tab_standings, tab_players, tab_pairs, tab_matches, tab_upcoming, tab_availability = st.tabs(
    ["Stilling", "Spillere", "Makkerpar", "Kampe", "Kommende", "Tilgængelighed"]
)

with tab_standings:
    st.subheader("Puljestilling")
    if standings.empty:
        st.info("Puljestillingen kunne ikke hentes.")
    else:
        show = standings.rename(columns={
            "standing": "#", "team_name": "Hold", "match_points": "Pts", "played": "Sp",
            "wins": "V", "draws": "U", "losses": "T", "sets_diff": "Sæt±", "games_diff": "Games±",
        })[["#", "Hold", "Pts", "Sp", "V", "U", "T", "Sæt±", "Games±", "participant_id"]]

        def highlight_us(row):
            return ["background-color: rgba(99,153,255,0.18); font-weight: 600;"] * len(row) if row["participant_id"] == our_participant_id else [""] * len(row)

        st.dataframe(
            show.style.apply(highlight_us, axis=1).format({"Sæt±": "{:+d}", "Games±": "{:+d}"}).hide(subset=["participant_id"], axis=1),
            use_container_width=True,
            hide_index=True,
        )

with tab_players:
    st.subheader("Spillerstatistik")
    st.caption("Primært baseret på individuelle kampe: hvor mange doublekampe hver spiller har spillet, vundet og tabt. Sæt og games vises som ekstra detaljer.")

    player_stats = player_set_stats(individual)
    if player_stats.empty:
        st.info("Ingen individuelle matches i data endnu.")
    else:
        main_cols = ["Spiller", "Ind. kampe", "Match V", "Match T", "Match %"]
        detail_cols = ["Sæt vundet", "Sæt tabt", "Sæt±", "Sæt %", "Games vundet", "Games tabt", "Games±"]
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
            "doubles_played": "Ind. spillet", "total_games_won": "Games vundet",
            "total_games_lost": "Games tabt", "games_diff": "Games±",
        }).copy()
        overview["Dato"] = overview["Dato"].dt.strftime("%d/%m/%Y")
        overview["H/U"] = overview["H/U"].map({"home": "Hjemme", "away": "Ude"}).fillna(overview["H/U"])
        overview["Resultat"] = overview.apply(lambda r: f"{fmt_int(r['Os'])}–{fmt_int(r['Dem'])}", axis=1)
        st.dataframe(overview[["Runde", "Dato", "Modstander", "H/U", "Resultat", "Ind. vundet", "Ind. spillet", "Games vundet", "Games tabt", "Games±"]], use_container_width=True, hide_index=True)

        played["label"] = played.apply(lambda r: f"R{r['round']} · {r['datetime'].strftime('%d/%m')} · {r['opponent']}", axis=1)
        choice = st.selectbox("Vælg kamp for detaljer", played["label"].tolist())
        tm_id = played.loc[played["label"] == choice, "team_match_id"].iloc[0]
        chosen = played[played["team_match_id"] == tm_id].iloc[0]
        sub = individual[individual["team_match_id"] == tm_id].copy()

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Holdkamp", f"{fmt_int(chosen['our_score'])} – {fmt_int(chosen['their_score'])}")
        c2.metric("Udfald", "Vundet" if chosen["won"] else "Tabt")
        c3.metric("Individuelle", f"{fmt_int(chosen.get('doubles_won'))} / {fmt_int(chosen.get('doubles_played'))}")
        c4.metric("Games", f"{fmt_int(chosen.get('total_games_won'))} – {fmt_int(chosen.get('total_games_lost'))}")
        c5.metric("Games±", fmt_signed(chosen.get("games_diff")))

        if not sub.empty:
            st.markdown("**Individuelle kampe**")
            st.dataframe(match_detail_table(sub), use_container_width=True, hide_index=True)
            st.markdown("**Spillerbidrag i valgt holdkamp**")
            st.dataframe(player_contribution_table(sub), use_container_width=True, hide_index=True)

with tab_upcoming:
    st.subheader("Kommende kampe")
    upcoming = team_matches[~team_matches["played"]].copy() if not team_matches.empty else pd.DataFrame()
    if upcoming.empty:
        st.success("Ingen kommende kampe i denne sæson.")
    else:
        for _, r in upcoming.iterrows():
            with st.container(border=True):
                venue = "Hjemme" if r["venue"] == "home" else "Ude"
                st.markdown(f"**Runde {r['round']} · {r['opponent']}**  \\n{r['datetime'].strftime('%d/%m/%Y %H:%M')} · {venue} · {r['location'] or '—'}")

with tab_availability:
    st.subheader("Tilgængelighed")
    matches = availability.get("matches", [])
    players_df = availability.get("players", pd.DataFrame())
    if not matches:
        st.info("Kunne ikke hente eller parse tilgængelighedsarket.")
    else:
        titles = [m["title"] for m in matches]
        selected_title = st.selectbox("Vælg kamp", titles)
        selected_match = next(m for m in matches if m["title"] == selected_title)
        st.metric("Antal der kan", selected_match["available_count"])
        table = selected_match["table"].copy()
        only_available = st.checkbox("Vis kun spillere der kan spille", value=True)
        if only_available:
            table = table[table["Kan spille"] == "Ja"].copy()
        st.dataframe(table, use_container_width=True, hide_index=True)
        if not players_df.empty:
            st.subheader("Samlet spilleroversigt")
            st.dataframe(players_df, use_container_width=True, hide_index=True)

st.divider()
st.caption(f"Data hentet fra rankedin.com · {len(team_matches)} holdkampe · {len(individual)} individuelle matches parsed.")
