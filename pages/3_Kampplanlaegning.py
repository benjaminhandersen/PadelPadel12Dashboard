import streamlit as st
from app_config import get_active_season, load_config
from fines_connection import require_app_login
from navigation import render_navigation
from planning_ui import render_planning

st.set_page_config(page_title='Kampplanlægning', page_icon='📅', layout='centered')
backend = require_app_login()
render_navigation()
config = load_config()
active_key, _ = get_active_season(config)
seasons = config['seasons']
season = st.sidebar.selectbox('Vælg sæson', list(seasons),
    index=list(seasons).index(active_key), format_func=lambda key: seasons[key].get('label', key))
render_planning(backend, season, seasons[season].get('label', season))
