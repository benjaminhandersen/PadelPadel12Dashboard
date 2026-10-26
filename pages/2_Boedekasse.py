import streamlit as st
from fines_ui import render_fines

st.set_page_config(page_title='Bødekassen', page_icon='💰', layout='centered')
render_fines()
