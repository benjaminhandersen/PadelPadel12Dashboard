from __future__ import annotations

import pandas as pd
import streamlit as st

from padel_pipeline import build_dataset
from app_config import load_config, get_active_season, set_active_season, upsert_season

st.set_page_config(page_title="Padel Dashboard", page_icon="🎾", layout="wide")

cfg = load_config()
active_key, active = get_active_season(cfg)
seasons = cfg.get("seasons", {})

st.sidebar.header("Sæson")

labels = {k: v.get("label", k) for k, v in seasons.items()}
keys = list(labels.keys())
values = list(labels.values())

selected_label = st.sidebar.selectbox("Vælg sæson", options=values, index=values.index(labels.get(active_key)))
selected_key = keys[values.index(selected_label)]

if selected_key != active_key:
    set_active_season(selected_key)
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.subheader("Tilføj ny sæson")

new_label = st.sidebar.text_input("Navn")
new_team_url = st.sidebar.text_input("Team link")
new_pool_url = st.sidebar.text_input("Pool link (valgfri)")

if st.sidebar.button("Gem"):
    if new_label and new_team_url:
        upsert_season(new_label, new_team_url, new_pool_url)
        st.sidebar.success("Gemt")
        st.rerun()

team_id = active.get("team_id")
pool_id = active.get("pool_id")
season_name = active.get("label")

@st.cache_data(ttl=60*15)
def load_data(team_id, pool_id):
    return build_dataset(team_id, pool_id)

with st.spinner("Henter data..."):
    data = load_data(team_id, pool_id)

standings = data["standings"]

our_row = standings[standings["participant_id"] == team_id] if not standings.empty else pd.DataFrame()
our_name = our_row["team_name"].iloc[0] if not our_row.empty else f"Team {team_id}"

st.title(our_name)
st.caption(season_name)

st.write("Multi-sæson aktiv")
