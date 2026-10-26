"""Shared-password gate; credentials stay on the Streamlit server."""
import hashlib
import hmac
import os

import streamlit as st


def read_settings():
    try:
        return st.secrets.to_dict()
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        return {}


def shared_credentials():
    settings = read_settings()
    password = os.environ.get('APP_PASSWORD') or settings.get('access', {}).get('password', '')
    secret_key = os.environ.get('SUPABASE_SECRET_KEY') or settings.get('supabase', {}).get('secret_key', '')
    return password, secret_key


def password_version(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def shared_authorized():
    password, _ = shared_credentials()
    return bool(password) and hmac.compare_digest(
        st.session_state.get('shared_password_version', ''), password_version(password))


def shared_login(password, show_account=True):
    if not shared_authorized():
        # Personal-account sessions must not bypass shared-password mode.
        st.session_state.pop('fines_auth', None)
        st.caption('Indtast holdets fælles adgangskode for at åbne appen.')
        with st.form('shared_login', clear_on_submit=True):
            supplied = st.text_input('Fælles adgangskode', type='password', key='shared_password_input')
            if st.form_submit_button('Åbn dashboard', use_container_width=True):
                if hmac.compare_digest(supplied.encode('utf-8'), password.encode('utf-8')):
                    st.session_state['shared_password_version'] = password_version(password)
                    st.rerun()
                else:
                    st.error('Forkert adgangskode.')
        return False
    if show_account and st.button('Log ud', key='shared_logout'):
        st.session_state.clear()
        st.rerun()
    return True
