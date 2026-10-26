import streamlit as st
from fines_ui import render_fines
from fines_connection import require_app_login
from app_config import get_active_season, load_config
from lineup_optimizer import all_known_players
from padel_pipeline import build_dataset

st.set_page_config(page_title='Bødekassen', page_icon='💰', layout='centered')
fines_backend = require_app_login()

@st.cache_data(ttl=60 * 15)
def load_players(team_id, pool_id):
    data = build_dataset(team_id, pool_id)
    return all_known_players(data['individual'], data['lineup']).to_dict('records')

_, active = get_active_season(load_config())
try:
    players = load_players(int(active['team_id']), int(active['pool_id']))
except Exception:
    st.warning('Kunne ikke hente holdspillere fra Rankedin. Overblik og historik kan stadig åbnes.')
    players = []
render_fines(players, store=fines_backend)
