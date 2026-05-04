"""
Padel dashboard — Streamlit UI
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from padel_pipeline import build_dataset, stat_best_pairs, stat_per_match, stat_win_loss
from app_config import load_config, save_config, extract_team_id_from_url, extract_pool_id_from_url

# Load config
cfg = load_config()
team_id = cfg.get("team_id", 2701885)
pool_id = cfg.get("pool_id", 11353)
season_name = cfg.get("season_name", "Padel Liga")

st.set_page_config(page_title="Padel Dashboard", page_icon="🎾", layout="wide")

# Sidebar config
st.sidebar.header("⚙️ Setup (én gang pr. sæson)")

team_url = st.sidebar.text_input("Team link", value=cfg.get("team_url", ""))
pool_url = st.sidebar.text_input("Pool link", value=cfg.get("pool_url", ""))
season_input = st.sidebar.text_input("Sæson navn", value=season_name)

if st.sidebar.button("Gem config"):
    new_team_id = extract_team_id_from_url(team_url) or team_id
    new_pool_id = extract_pool_id_from_url(pool_url) or pool_id

    new_cfg = {
        "team_url": team_url,
        "pool_url": pool_url,
        "team_id": new_team_id,
        "pool_id": new_pool_id,
        "season_name": season_input,
    }
    save_config(new_cfg)
    st.success("Config gemt — genindlæs siden")
    st.stop()

# Refresh
if st.sidebar.button("🔄 Opdater data"):
    st.cache_data.clear()
    st.rerun()

@st.cache_data(ttl=60*15)
def load_data(team_id, pool_id):
    return build_dataset(team_id, pool_id)

with st.spinner("Henter data..."):
    data = load_data(team_id, pool_id)

team_matches = data["team_matches"]
individual = data["individual"]
lineup = data["lineup"]
standings = data["standings"]
per_match = stat_per_match(team_matches, individual)

our_row = standings[standings["participant_id"] == team_id] if not standings.empty else pd.DataFrame()
our_name = our_row["team_name"].iloc[0] if not our_row.empty else f"Team {team_id}"

st.title(our_name)
st.caption(season_name)

st.write("Dashboard kører nu med dynamisk config ✅")
