"""
Padel dashboard — Streamlit UI
===============================
Kør med:  streamlit run dashboard.py
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from padel_pipeline import (
    OUR_TEAM_ID,
    OUR_POOL_ID,
    build_dataset,
    stat_best_pairs,
    stat_per_match,
    stat_win_loss,
)


# ============================================================
# Sideopsætning
# ============================================================
st.set_page_config(
    page_title="Padel Dashboard",
    page_icon="🎾",
    layout="wide",
)


# ============================================================
# Hjælpefunktioner
# ============================================================
def fmt_pair(row: pd.Series, prefix: str) -> str:
    return f"{row[f'{prefix}_p1_name']} & {row[f'{prefix}_p2_name']}"


def fmt_int(value, default: str = "—") -> str:
    if pd.isna(value):
        return default
    return str(int(value))


def fmt_signed(value, default: str = "—") -> str:
    if pd.isna(value):
        return default
    return f"{int(value):+d}"


def match_detail_table(sub: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in sub.iterrows():
        rows.append({
            "Udfald": "✅ Vundet" if r["won"] else "❌ Tabt",
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


def match_highlights(sub: pd.DataFrame) -> dict[str, str]:
    if sub.empty:
        return {
            "best": "—",
            "closest": "—",
            "largest_loss": "—",
        }

    best = sub.sort_values("games_diff", ascending=False).iloc[0]
    closest = sub.assign(abs_diff=sub["games_diff"].abs()).sort_values("abs_diff").iloc[0]
    losses = sub[~sub["won"]].copy()

    if losses.empty:
        largest_loss_text = "Ingen tabte individuelle kampe"
    else:
        largest_loss = losses.sort_values("games_diff").iloc[0]
        largest_loss_text = (
            f"{fmt_pair(largest_loss, 'our')} ({largest_loss['sets_str']}, "
            f"{int(largest_loss['games_diff']):+d})"
        )

    return {
        "best": f"{fmt_pair(best, 'our')} ({best['sets_str']}, {int(best['games_diff']):+d})",
        "closest": f"{fmt_pair(closest, 'our')} ({closest['sets_str']}, {int(closest['games_diff']):+d})",
        "largest_loss": largest_loss_text,
    }


def player_contribution_table(sub: pd.DataFrame) -> pd.DataFrame:
    if sub.empty:
        return pd.DataFrame()

    p1 = sub[["our_p1_id", "our_p1_name", "won", "games_won", "games_lost", "games_diff"]].rename(
        columns={"our_p1_id": "player_id", "our_p1_name": "Spiller"}
    )
    p2 = sub[["our_p2_id", "our_p2_name", "won", "games_won", "games_lost", "games_diff"]].rename(
        columns={"our_p2_id": "player_id", "our_p2_name": "Spiller"}
    )
    per_player = pd.concat([p1, p2], ignore_index=True)

    out = (
        per_player.groupby(["player_id", "Spiller"])
        .agg(
            Kampe=("won", "count"),
            V=("won", "sum"),
            Games_vundet=("games_won", "sum"),
            Games_tabt=("games_lost", "sum"),
            Games_diff=("games_diff", "sum"),
        )
        .reset_index()
    )
    out["T"] = out["Kampe"] - out["V"]
    out["Win %"] = (out["V"] / out["Kampe"] * 100).round(1)

    return (
        out.rename(columns={
            "Games_vundet": "Games vundet",
            "Games_tabt": "Games tabt",
            "Games_diff": "Games±",
        })[["Spiller", "Kampe", "V", "T", "Win %", "Games vundet", "Games tabt", "Games±"]]
        .sort_values(["V", "Games±", "Kampe"], ascending=[False, False, False])
        .reset_index(drop=True)
    )


# ============================================================
# Data (cached, så Streamlit ikke kalder Rankedin ved hver re-render)
# ============================================================
@st.cache_data(ttl=60 * 15)
def load_data(team_id: int, pool_id: int, refresh: bool = False):
    return build_dataset(our_team_id=team_id, pool_id=pool_id, refresh=refresh)


# ============================================================
# Sidebar — kontroller
# ============================================================
st.sidebar.header("Indstillinger")

team_id = st.sidebar.number_input("Team ID", value=OUR_TEAM_ID, step=1)
pool_id = st.sidebar.number_input("Pool ID", value=OUR_POOL_ID, step=1)

if st.sidebar.button("🔄 Opdater fra Rankedin"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.caption(
    "Data caches i 15 min. Klik knappen eller slet `cache/`-mappen for friske data."
)


# ============================================================
# Hent data
# ============================================================
with st.spinner("Henter data fra Rankedin..."):
    try:
        data = load_data(team_id, pool_id)
    except Exception as e:
        st.error(f"Fejl ved dataindlæsning: {e}")
        st.info(
            "Hvis det er første kørsel: bekræft URL'erne i `padel_pipeline.py` "
            "matcher dem du ser i browserens DevTools."
        )
        st.stop()

team_matches = data["team_matches"]
individual = data["individual"]
lineup = data["lineup"]
standings = data["standings"]
availability = data.get("availability", {"raw": pd.DataFrame(), "players": pd.DataFrame(), "matches": []})
per_match = stat_per_match(team_matches, individual)


# ============================================================
# Header + nøgletal
# ============================================================
our_row = standings[standings["participant_id"] == team_id] if not standings.empty else pd.DataFrame()
our_name = our_row["team_name"].iloc[0] if not our_row.empty else f"Team {team_id}"

st.title(our_name)
st.caption("Lunar Ligaen Forår 2026 · Serie 3-B Vest · kilde: rankedin.com")

col1, col2, col3, col4 = st.columns(4)

if not our_row.empty:
    s = our_row.iloc[0]
    col1.metric("Placering", f"{s['standing']} / {len(standings)}")
    col2.metric("Kampe", f"{s['played']} / 7")
    col3.metric("Vundet / tabt", f"{s['wins']} / {s['losses']}")
    col4.metric("Games-diff", f"{s['games_diff']:+d}")
else:
    played = int(team_matches["played"].sum())
    won = int(team_matches["won"].fillna(False).sum())
    col1.metric("Placering", "—")
    col2.metric("Kampe", f"{played} / {len(team_matches)}")
    col3.metric("Vundet / tabt", f"{won} / {played - won}")
    col4.metric("Games-diff", "—")


# ============================================================
# Tabs
# ============================================================
tab_standings, tab_players, tab_pairs, tab_matches, tab_upcoming, tab_availability = st.tabs(
    ["Stilling", "Spillere", "Makkerpar", "Kampe", "Kommende", "Tilgængelighed"]
)


# ---------- Stilling ----------
with tab_standings:
    st.subheader("Puljestilling")
    if standings.empty:
        st.info(
            "Stillings-endpointet kunne ikke hentes endnu. "
            "Dashboardet virker stadig uden denne del."
        )
    else:
        def highlight_us(row):
            return ["background-color: rgba(99, 153, 255, 0.15);"] * len(row) \
                if row["participant_id"] == team_id else [""] * len(row)

        show = standings.rename(columns={
            "standing": "#",
            "team_name": "Hold",
            "match_points": "Pts",
            "played": "Sp",
            "wins": "V",
            "draws": "U",
            "losses": "T",
            "sets_diff": "Sæt±",
            "games_diff": "Games±",
        })[["#", "Hold", "Pts", "Sp", "V", "U", "T", "Sæt±", "Games±", "participant_id"]]

        st.dataframe(
            show.style.apply(highlight_us, axis=1)
                .format({"Sæt±": "{:+d}", "Games±": "{:+d}"})
                .hide(subset=["participant_id"], axis=1),
            use_container_width=True,
            hide_index=True,
        )


# ---------- Spillere ----------
with tab_players:
    st.subheader("Win / loss pr. spiller")

    wl = stat_win_loss(individual, lineup)
    if wl.empty:
        st.info("Ingen individuelle matches i data endnu.")
    else:
        show = wl.rename(columns={
            "name": "Spiller",
            "played": "Sp",
            "wins": "V",
            "losses": "T",
            "win_pct": "Win %",
            "ranking_pts": "Ranking pts",
            "role": "Rolle",
        })
        cols = ["Spiller", "Sp", "V", "T", "Win %"]
        if "Ranking pts" in show.columns:
            cols += ["Ranking pts"]
        if "Rolle" in show.columns:
            cols += ["Rolle"]

        st.dataframe(show[cols], use_container_width=True, hide_index=True)

        chart_df = wl.set_index("name")[["wins", "losses"]]
        st.bar_chart(chart_df, horizontal=True, height=300)

    if lineup is not None and not lineup.empty:
        st.subheader("Trup (ikke nødvendigvis spillet endnu)")
        roster = lineup.rename(columns={
            "full_name": "Navn",
            "ranking_pts": "Ranking pts",
            "rating_begin": "Rating",
            "has_license": "Licens",
            "role": "Rolle",
        })[["Navn", "Ranking pts", "Rating", "Licens", "Rolle"]]
        st.dataframe(roster, use_container_width=True, hide_index=True)


# ---------- Makkerpar ----------
with tab_pairs:
    st.subheader("Bedste makkerpar")

    min_matches = st.slider("Minimum antal kampe", 1, 10, 1)
    pairs = stat_best_pairs(individual, min_matches=min_matches)

    if pairs.empty:
        st.info(f"Ingen makkerpar med mindst {min_matches} kampe endnu.")
    else:
        show = pairs.rename(columns={
            "pair_name": "Par",
            "played": "Sp",
            "wins": "V",
            "losses": "T",
            "win_pct": "Win %",
        })[["Par", "Sp", "V", "T", "Win %"]]
        st.dataframe(show, use_container_width=True, hide_index=True)


# ---------- Kampe ----------
with tab_matches:
    st.subheader("Kampstatistik")

    played = per_match[per_match["played"]].copy()
    if played.empty:
        st.info("Ingen spillede kampe i data.")
    else:
        overview = played.rename(columns={
            "round": "Runde",
            "datetime": "Dato",
            "opponent": "Modstander",
            "venue": "H/U",
            "our_score": "Os",
            "their_score": "Dem",
            "doubles_won": "Ind. vundet",
            "doubles_played": "Ind. spillet",
            "total_games_won": "Games vundet",
            "total_games_lost": "Games tabt",
            "games_diff": "Games±",
        }).copy()
        overview["Dato"] = overview["Dato"].dt.strftime("%d/%m/%Y")
        overview["H/U"] = overview["H/U"].map({"home": "Hjemme", "away": "Ude"}).fillna(overview["H/U"])
        overview["Resultat"] = overview.apply(
            lambda r: f"{fmt_int(r['Os'])}–{fmt_int(r['Dem'])}",
            axis=1,
        )

        st.markdown("**Samlet kampoversigt**")
        st.dataframe(
            overview[[
                "Runde",
                "Dato",
                "Modstander",
                "H/U",
                "Resultat",
                "Ind. vundet",
                "Ind. spillet",
                "Games vundet",
                "Games tabt",
                "Games±",
            ]],
            use_container_width=True,
            hide_index=True,
        )

        played["label"] = played.apply(
            lambda r: f"R{r['round']} · {r['datetime'].strftime('%d/%m')} · "
                      f"{r['opponent']} ({'hjemme' if r['venue']=='home' else 'ude'})",
            axis=1,
        )
        choice = st.selectbox("Vælg kamp for detaljer", played["label"].tolist())
        tm_id = played.loc[played["label"] == choice, "team_match_id"].iloc[0]
        chosen = played[played["team_match_id"] == tm_id].iloc[0]
        sub = individual[individual["team_match_id"] == tm_id].copy()

        st.divider()
        st.markdown(f"### Runde {chosen['round']} mod {chosen['opponent']}")

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Holdkamp", f"{fmt_int(chosen['our_score'])} – {fmt_int(chosen['their_score'])}")
        c2.metric("Udfald", "✅ Vundet" if chosen["won"] else "❌ Tabt")
        c3.metric("Individuelle", f"{fmt_int(chosen.get('doubles_won'))} / {fmt_int(chosen.get('doubles_played'))}")
        c4.metric("Games", f"{fmt_int(chosen.get('total_games_won'))} – {fmt_int(chosen.get('total_games_lost'))}")
        c5.metric("Games±", fmt_signed(chosen.get("games_diff")))

        venue = "Hjemme" if chosen["venue"] == "home" else "Ude"
        st.caption(
            f"{chosen['datetime'].strftime('%d/%m/%Y %H:%M')} · {venue} · "
            f"{chosen['location'] or 'Ukendt spillested'}"
        )

        if sub.empty:
            st.info("Ingen detaljer fundet for denne holdkamp.")
        else:
            highlights = match_highlights(sub)
            h1, h2, h3 = st.columns(3)
            h1.info(f"**Bedste individuelle kamp**\n\n{highlights['best']}")
            h2.info(f"**Tætteste kamp**\n\n{highlights['closest']}")
            h3.info(f"**Største nederlag**\n\n{highlights['largest_loss']}")

            st.markdown("**Individuelle kampe**")
            details = match_detail_table(sub)
            st.dataframe(
                details.style.format({
                    "Games±": "{:+d}",
                    "Win %": "{:.1f}",
                }),
                use_container_width=True,
                hide_index=True,
            )

            st.markdown("**Spillerbidrag i valgt holdkamp**")
            contrib = player_contribution_table(sub)
            st.dataframe(
                contrib.style.format({"Games±": "{:+d}", "Win %": "{:.1f}"}),
                use_container_width=True,
                hide_index=True,
            )


# ---------- Kommende ----------
with tab_upcoming:
    st.subheader("Kommende kampe")

    upcoming = team_matches[~team_matches["played"]].copy()
    if upcoming.empty:
        st.success("Ingen kampe tilbage i sæsonen.")
    else:
        for _, r in upcoming.iterrows():
            with st.container(border=True):
                c1, c2, c3 = st.columns([1, 3, 2])
                c1.markdown(f"**Runde {r['round']}**")
                c2.markdown(f"**{r['opponent']}**  \n"
                            f"_{r['location'] or '—'}_")
                venue = "Hjemme" if r["venue"] == "home" else "Ude"
                c3.markdown(f"{r['datetime'].strftime('%a %d. %b %Y, %H:%M')}  \n"
                            f"_{venue}_")


# ---------- Tilgængelighed ----------
with tab_availability:
    st.subheader("Tilgængelighed pr. kamp")

    matches = availability.get("matches", [])
    players_df = availability.get("players", pd.DataFrame())

    if not matches:
        st.info("Kunne ikke hente eller parse tilgængelighedsarket.")
    else:
        campaign_titles = [m["title"] for m in matches]
        selected_title = st.selectbox("Vælg kamp", campaign_titles)

        selected_match = next(m for m in matches if m["title"] == selected_title)
        match_table = selected_match["table"].copy()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Dato", selected_match["date"] or "—")
        c2.metric("Tid", selected_match["time"] or "—")
        c3.metric("Modstander", selected_match["away"] or "—")
        c4.metric("Antal der kan", selected_match["available_count"])

        only_available = st.checkbox("Vis kun spillere der kan spille", value=True)

        if only_available:
            match_table = match_table[match_table["Kan spille"] == "Ja"].copy()

        def highlight_yes(val):
            if val == "Ja":
                return "background-color: rgba(80, 200, 120, 0.20); font-weight: 600;"
            return ""

        st.dataframe(
            match_table.style.map(highlight_yes, subset=["Kan spille"]),
            use_container_width=True,
            hide_index=True,
        )

        st.divider()
        st.subheader("Samlet spilleroversigt")

        if not players_df.empty:
            st.dataframe(players_df, use_container_width=True, hide_index=True)


# ============================================================
# Footer
# ============================================================
st.divider()
st.caption(
    f"Data hentet fra rankedin.com · "
    f"{len(team_matches)} holdkampe · "
    f"{len(individual)} individuelle matches parsed."
)
