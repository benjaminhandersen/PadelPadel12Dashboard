"""Streamlit connection/login UI for the shared ledger."""
import os
import json
from pathlib import Path
import streamlit as st

from supabase_fines import FinesError, SupabaseFines


def get_store(show_account=True):
    # Explicit local database is reserved for development/tests.
    if os.environ.get('PADEL_FINES_DB'):
        import fines_store
        return fines_store
    try:
        config = st.secrets.get('supabase', {})
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        config = {}
    public_path = Path(__file__).with_name('supabase_public.json')
    public = json.loads(public_path.read_text(encoding='utf-8')) if public_path.exists() else {}
    url = os.environ.get('SUPABASE_URL') or config.get('url') or public.get('url')
    key = os.environ.get('SUPABASE_PUBLISHABLE_KEY') or config.get('publishable_key') or public.get('publishable_key')
    if not url or not key:
        st.info('Appen mangler Supabase-forbindelsen. Administratoren skal tilføje projektets URL og publishable key i Streamlit Secrets.')
        return None
    state = st.session_state.setdefault('fines_auth', {})
    try:
        backend = SupabaseFines(url, key, state)
        backend.refresh()
    except FinesError as exc:
        st.error(str(exc))
        return None
    if not state.get('access_token'):
        st.caption('Log ind med din holdkonto. Nye konti skal godkendes af administratoren.')
        mode = st.radio('Konto', ['Log ind', 'Opret konto'], horizontal=True, key='fines_login_mode')
        with st.form('fines_login', clear_on_submit=True):
            email = st.text_input('E-mail')
            password = st.text_input('Adgangskode', type='password')
            if st.form_submit_button(mode, use_container_width=True):
                try:
                    if not email.strip() or not password:
                        raise FinesError('Udfyld e-mail og adgangskode.')
                    if mode == 'Opret konto':
                        if len(password) < 12:
                            raise FinesError('Vælg en adgangskode på mindst 12 tegn.')
                        if not backend.signup(email, password):
                            st.success('Hvis oprettelsen kan gennemføres, modtager du en bekræftelse på e-mail. Bekræft og log derefter ind.')
                            return None
                    else:
                        backend.login(email, password)
                    st.rerun()
                except FinesError as exc:
                    st.error(str(exc))
        return None
    if show_account:
        st.caption('Logget ind som ' + state.get('email', 'holdmedlem'))
    if show_account and st.button('Log ud', key='fines_logout'):
        try:
            backend.logout()
        except FinesError:
            pass
        st.rerun()
    return backend


def require_app_login():
    """Gate every entry point before loading Rankedin or showing team data."""
    if not st.session_state.get('fines_auth', {}).get('access_token'):
        st.title('🎾 Padel Dashboard')
    backend = get_store()
    if backend is None:
        st.stop()
    if isinstance(backend, SupabaseFines):
        try:
            # The database validates the JWT and approved membership on every rerun.
            backend.snapshot()
        except FinesError as exc:
            st.error(str(exc))
            st.stop()
    return backend
