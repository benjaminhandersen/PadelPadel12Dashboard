import streamlit as st

from padel_pipeline import OUR_TEAM_ID, OUR_POOL_ID, build_dataset
from lineup_optimizer import (
    all_known_players,
    suggest_two_round_lineups,
    selected_pair_history,
)

st.set_page_config(page_title="Holdforslag", page_icon="🎯", layout="wide")

st.title("🎯 Holdforslag")
st.caption("2 runder · 3 par pr. runde · samme par kun én gang")

@st.cache_data(ttl=60*15)
def load_data():
    return build_dataset(OUR_TEAM_ID, OUR_POOL_ID)

with st.spinner("Henter data..."):
    data = load_data()

individual = data["individual"]
lineup = data["lineup"]
team_matches = data["team_matches"]

players = all_known_players(individual, lineup)

if players.empty:
    st.info("Ingen spillere fundet endnu")
    st.stop()

names = players["name"].tolist()
name_to_id = dict(zip(players["name"], players["player_id"]))

upcoming = team_matches[~team_matches["played"]]
if not upcoming.empty:
    upcoming["label"] = upcoming.apply(
        lambda r: f"R{r['round']} · {r['datetime'].strftime('%d/%m')} · {r['opponent']}", axis=1
    )
    st.selectbox("Kamp", upcoming["label"])

selected = st.multiselect(
    "Vælg spillere der kan spille",
    options=names,
    default=names[:6]
)

ids = [name_to_id[n] for n in selected]

if len(ids) < 6:
    st.warning("Du skal vælge mindst 6 spillere")
else:
    results = suggest_two_round_lineups(ids, players, individual, max_results=10)

    if results.empty:
        st.info("Ingen forslag")
    else:
        best = results.iloc[0]

        st.subheader("Bedste forslag")
        st.write(best[[
            "Round 1 - Par 1","Round 1 - Par 2","Round 1 - Par 3",
            "Round 2 - Par 1","Round 2 - Par 2","Round 2 - Par 3",
        ]])

        st.metric("Score", best["Score"])
        st.metric("Sejre", best["Historiske sejre"])

        st.subheader("Alle forslag")
        st.dataframe(results)

        st.subheader("Makkerpar historik")
        hist = selected_pair_history(ids, individual)
        st.dataframe(hist.drop(columns=["pair_key"]))
