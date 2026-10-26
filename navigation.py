"""Shared sidebar labels without changing the deployed entrypoint URL."""
import streamlit as st


def render_navigation():
    st.sidebar.markdown('### PadelPadel 12')
    st.sidebar.page_link('dashboard.py', label='Holdoverblik', icon='🏠')
    st.sidebar.page_link('pages/1_Holdforslag.py', label='Holdforslag', icon='🎯')
    st.sidebar.page_link('pages/2_Boedekasse.py', label='Bødekassen', icon='💰')
    st.sidebar.page_link('pages/3_Kampplanlaegning.py', label='Kampplanlægning', icon='📅')
    st.sidebar.divider()
