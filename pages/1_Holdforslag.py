import streamlit as st
from fines_connection import require_app_login
from navigation import render_navigation
from lineup_ui import render_lineup_suggestions
from lineup_history import load_lineup_history

from app_config import get_active_season, load_config
from padel_pipeline import build_dataset
from lineup_optimizer import (
    all_known_players,
    suggest_two_round_lineups,
    selected_pair_history,
)

st.set_page_config(page_title="Holdforslag", page_icon="🎯", layout="wide")
require_app_login()
render_navigation()

DATA_CACHE_VERSION = 5

st.title("🎯 Holdforslag")
st.caption("2 runder · 3 par pr. runde · samme par kun én gang")

config = load_config()
active_key, active = get_active_season(config)
team_id = int(active.get("team_id"))
pool_id = int(active.get("pool_id"))


@st.cache_data(ttl=60*15)
def load_data(team_id: int, pool_id: int, cache_version: int):
    return build_dataset(team_id, pool_id)

@st.cache_data(ttl=60*15)
def load_history(seasons, cache_version):
    return load_lineup_history(seasons)


with st.spinner("Henter data fra alle sæsoner..."):
    data = load_data(team_id, pool_id, DATA_CACHE_VERSION)
    history, history_seasons, history_warnings = load_history(config["seasons"], DATA_CACHE_VERSION)

individual = data["individual"]
lineup = data["lineup"]
team_matches = data["team_matches"]
standings = data["standings"]

players = all_known_players(individual, lineup)
# Use current roster names for historical IDs, including earlier name changes.
current_names = dict(zip(players["player_id"], players["name"]))
if not history.empty:
    for side in (1, 2):
        history[f"our_p{side}_name"] = history[f"our_p{side}_id"].map(current_names).fillna(history[f"our_p{side}_name"])
st.caption(f"Vurderingsgrundlag: alle {len(history_seasons)} indlæste sæsoner · {len(history)} kampe. Alle sæsoner vægter ens.")
for warning in history_warnings:
    st.warning(warning)
if history_warnings:
    st.warning("Historikken er ufuldstændig. Forslagene bruger de kampe, der kunne indlæses.")

# ---------- Puljestilling ----------
with st.expander("📊 Puljestilling", expanded=False):
    if standings.empty:
        st.info("Puljestillingen kunne ikke hentes endnu.")
    else:
        show = standings.rename(columns={
            "standing": "#",
            "team_name": "Hold",
            "match_points": "Pts",
            "played": "Sp",
            "wins": "V",
            "draws": "U",
            "losses": "T",
            "sets_diff": "Sæt±",
            "games_diff": "Partier±",
        })[["#", "Hold", "Pts", "Sp", "V", "U", "T", "Sæt±", "Partier±", "participant_id"]]

        def highlight_us(row):
            configured_name = str(active.get("team_name", "")).replace(" ", "").replace("-", "").lower()
            row_name = str(row["Hold"]).replace(" ", "").replace("-", "").lower()
            if row["participant_id"] == team_id or (configured_name and configured_name in row_name):
                return ["background-color: rgba(99, 153, 255, 0.18); font-weight: 600;"] * len(row)
            return [""] * len(row)

        st.dataframe(
            show.style
                .apply(highlight_us, axis=1)
                .format({"Sæt±": "{:+d}", "Partier±": "{:+d}"})
                .hide(subset=["participant_id"], axis=1),
            use_container_width=True,
            hide_index=True,
        )

if players.empty:
    st.info("Ingen spillere fundet endnu")
    st.stop()

names = players["name"].tolist()
name_to_id = dict(zip(players["name"], players["player_id"]))

upcoming = team_matches[~team_matches["played"]].copy()
if not upcoming.empty:
    upcoming["label"] = upcoming.apply(
        lambda r: f"R{r['round']} · {r['datetime'].strftime('%d/%m')} · {r['opponent']}", axis=1
    )
    st.selectbox("Kamp", upcoming["label"])

st.subheader("1 · Vælg din trup")
selected = st.multiselect(
    "Vælg spillere der kan spille",
    options=names,
    default=names[:6]
)

st.caption(f"{len(selected)} spillere valgt · mindst 6 kræves til tre par pr. runde")
ids = [name_to_id[n] for n in selected]

if len(ids) < 6:
    st.warning("Du skal vælge mindst 6 spillere")
else:
    results = suggest_two_round_lineups(ids, players, history, max_results=10)

    if results.empty:
        st.info("Ingen forslag")
    else:
        st.subheader("2 · Se opstillingen")
        hist = selected_pair_history(ids, history)
        render_lineup_suggestions(results, hist, selected)
