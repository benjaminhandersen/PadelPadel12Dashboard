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
# Data (cached, så Streamlit ikke kalder Rankedin ved hver re-render)
# ============================================================
@st.cache_data(ttl=60 * 15)   # genopfrisk hver 15 min
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
individual   = data["individual"]
lineup       = data["lineup"]
standings    = data["standings"]


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
    won    = int(team_matches["won"].fillna(False).sum())
    col1.metric("Placering", "—")
    col2.metric("Kampe", f"{played} / {len(team_matches)}")
    col3.metric("Vundet / tabt", f"{won} / {played - won}")
    col4.metric("Games-diff", "—")


# ============================================================
# Tabs
# ============================================================
tab_standings, tab_players, tab_pairs, tab_matches, tab_upcoming = st.tabs(
    ["Stilling", "Spillere", "Makkerpar", "Kampe", "Kommende"]
)


# ---------- Stilling ----------
with tab_standings:
    st.subheader("Puljestilling")
    if standings.empty:
        st.info("Stillings-endpointet kunne ikke hentes. "
                "Bekræft URL'en i `padel_pipeline.py`.")
    else:
        def highlight_us(row):
            return ["background-color: rgba(99, 153, 255, 0.15);"] * len(row) \
                if row["participant_id"] == team_id else [""] * len(row)

        show = standings.rename(columns={
            "standing":     "#",
            "team_name":    "Hold",
            "match_points": "Pts",
            "played":       "Sp",
            "wins":         "V",
            "draws":        "U",
            "losses":       "T",
            "sets_diff":    "Sæt±",
            "games_diff":   "Games±",
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
            "name":        "Spiller",
            "played":      "Sp",
            "wins":        "V",
            "losses":      "T",
            "win_pct":     "Win %",
            "ranking_pts": "Ranking pts",
            "role":        "Rolle",
        })
        cols = ["Spiller", "Sp", "V", "T", "Win %"]
        if "Ranking pts" in show.columns: cols += ["Ranking pts"]
        if "Rolle" in show.columns:       cols += ["Rolle"]
        st.dataframe(show[cols], use_container_width=True, hide_index=True)

        # Quick bar chart
        chart_df = wl.set_index("name")[["wins", "losses"]]
        st.bar_chart(chart_df, horizontal=True, height=300)

    if lineup is not None and not lineup.empty:
        st.subheader("Trup (ikke nødvendigvis spillet endnu)")
        roster = lineup.rename(columns={
            "full_name":    "Navn",
            "ranking_pts":  "Ranking pts",
            "rating_begin": "Rating",
            "has_license":  "Licens",
            "role":         "Rolle",
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
            "played":    "Sp",
            "wins":      "V",
            "losses":    "T",
            "win_pct":   "Win %",
        })[["Par", "Sp", "V", "T", "Win %"]]
        st.dataframe(show, use_container_width=True, hide_index=True)


# ---------- Kampe ----------
with tab_matches:
    st.subheader("Kampoversigt")

    played = team_matches[team_matches["played"]].copy()
    if played.empty:
        st.info("Ingen spillede kampe i data.")
    else:
        # Kampliste til valg
        played["label"] = played.apply(
            lambda r: f"R{r['round']} · {r['datetime'].strftime('%d/%m')} · "
                      f"{r['opponent']} ({'hjemme' if r['venue']=='home' else 'ude'})",
            axis=1,
        )
        choice = st.selectbox("Vælg kamp", played["label"].tolist())
        tm_id = played.loc[played["label"] == choice, "team_match_id"].iloc[0]

        chosen = played[played["team_match_id"] == tm_id].iloc[0]

        c1, c2, c3 = st.columns(3)
        c1.metric("Resultat", f"{int(chosen['our_score'])} – {int(chosen['their_score'])}")
        c2.metric("Sted", chosen["location"])
        c3.metric("Udfald", "✅ Vundet" if chosen["won"] else "❌ Tabt")

        st.divider()
        st.markdown("**Individuelle kampe**")

        sub = individual[individual["team_match_id"] == tm_id].copy()
        if sub.empty:
            st.info("Ingen detaljer fundet for denne holdkamp.")
        else:
            def fmt_pair(row, prefix):
                return f"{row[f'{prefix}_p1_name']} & {row[f'{prefix}_p2_name']}"

            rows = []
            for _, r in sub.iterrows():
                rows.append({
                    "Udfald": "✅" if r["won"] else "❌",
                    "Os":     fmt_pair(r, "our"),
                    "Modstandere": fmt_pair(r, "opp"),
                    "Sæt":    r["sets_str"],
                    "Games±": f"{r['games_diff']:+d}",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


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


# ============================================================
# Footer
# ============================================================
st.divider()
st.caption(
    f"Data hentet fra rankedin.com · "
    f"{len(team_matches)} holdkampe · "
    f"{len(individual)} individuelle matches parsed."
)
