"""Supabase REST client. Per-browser session credentials; never a service key."""
import time
from uuid import uuid4
from urllib.parse import urlparse

import requests


class FinesError(RuntimeError):
    pass


class SupabaseFines:
    def __init__(self, url, key, session_state):
        parsed = urlparse(url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.path not in ('', '/'):
            raise FinesError('Supabase URL skal være projektets HTTPS-adresse.')
        if not key.startswith('sb_publishable_'):
            raise FinesError('Brug en Supabase publishable key til bødekassen.')
        self.url = url.rstrip('/')
        self.key = key
        self.session = session_state

    def request(self, method, path, *, authenticated=True, **kwargs):
        headers = {'apikey': self.key}
        if authenticated:
            token = self.session.get('access_token')
            if not token:
                raise FinesError('Log ind for at åbne bødekassen.')
            headers['Authorization'] = 'Bearer ' + token
        headers.update(kwargs.pop('headers', {}))
        try:
            response = requests.request(method, self.url + path, headers=headers, timeout=20, **kwargs)
        except requests.RequestException as exc:
            raise FinesError('Ingen forbindelse til bødekassen. Opdater overblikket før du prøver igen.') from exc
        if response.status_code == 409:
            if method == 'POST' and path == '/rest/v1/padel_fines':
                fine_id = kwargs.get('json', {}).get('id')
                existing = self.request('GET', path, params={'id': 'eq.' + fine_id, 'select': '*'})
                if existing:
                    return existing
            raise FinesError('Registreringen findes allerede. Opdater overblikket.')
        if response.status_code in (401, 403):
            raise FinesError('Adgang afvist. Log ind igen, eller kontakt holdets administrator.')
        if not response.ok:
            # Do not expose credentials, request bodies or raw provider errors in UI/logs.
            raise FinesError(f'Supabase kunne ikke udføre handlingen (HTTP {response.status_code}).')
        return response.json() if response.content else None

    def login(self, email, password):
        data = self.request('POST', '/auth/v1/token?grant_type=password', authenticated=False,
                            json={'email': email.strip(), 'password': password})
        self.save_session(data)

    def signup(self, email, password):
        data = self.request('POST', '/auth/v1/signup', authenticated=False,
                            json={'email': email.strip(), 'password': password})
        if data.get('access_token'):
            self.save_session(data)
            return True
        return False

    def save_session(self, data):
        self.session.update(access_token=data['access_token'], refresh_token=data['refresh_token'],
                            expires_at=time.time() + data.get('expires_in', 3600),
                            email=data.get('user', {}).get('email', ''))

    def refresh(self):
        if self.session.get('access_token') and self.session.get('expires_at', 0) < time.time() + 60:
            try:
                data = self.request('POST', '/auth/v1/token?grant_type=refresh_token', authenticated=False,
                                    json={'refresh_token': self.session['refresh_token']})
                self.save_session(data)
            except FinesError:
                self.session.clear()
                raise

    def logout(self):
        try:
            if self.session.get('access_token'):
                self.request('POST', '/auth/v1/logout?scope=local')
        finally:
            self.session.clear()

    def snapshot(self):
        self.refresh()
        state = self.request('POST', '/rest/v1/rpc/padel_fines_snapshot', json={})
        if not state.get('role'):
            raise FinesError('Din konto har endnu ikke adgang til holdet. Kontakt administratoren.')
        return state

    def sync_roster(self, roster, state):
        if state['role'] != 'admin':
            return
        known = {p['player_id']: p['name'] for p in state.get('players', [])}
        for player in roster:
            player_id = int(player['player_id'])
            if player_id not in known:
                self.request('POST', '/rest/v1/padel_players',
                             headers={'Prefer': 'resolution=ignore-duplicates'},
                             json={'player_id': player_id, 'name': player['name']})
            elif known[player_id] != player['name']:
                self.request('PATCH', '/rest/v1/padel_players', params={'player_id': 'eq.' + str(player_id)},
                             json={'name': player['name']})

    def give_fine(self, player, reason, roster, request_id=None, player_id=None):
        matches = [p for p in roster if (p['player_id'] == player_id if player_id is not None else p['name'] == player)]
        if len(matches) != 1:
            raise FinesError('Spilleren findes ikke i det valgte holds Rankedin-data.')
        fine_id = request_id or str(uuid4())
        rows = self.request('POST', '/rest/v1/padel_fines', headers={'Prefer': 'return=representation'},
                            json={'id': fine_id, 'player_id': int(matches[0]['player_id']), 'reason': reason})
        return rows[0]['id'], rows[0]['amount']

    def set_cancelled(self, fine_id, cancelled):
        rows = self.request('PATCH', '/rest/v1/padel_fines', params={'id': 'eq.' + fine_id},
                            headers={'Prefer': 'return=representation'}, json={'cancelled': bool(cancelled)})
        if not rows:
            raise FinesError('Bøden blev ikke ændret. Opdater historikken.')

    def update_rate(self, reason, amount):
        if isinstance(amount, bool) or not isinstance(amount, int) or not 1 <= amount <= 10000:
            raise FinesError('Satsen skal være 1–10.000 hele kroner.')
        rows = self.request('PATCH', '/rest/v1/padel_rules', params={'name': 'eq.' + reason},
                            headers={'Prefer': 'return=representation'}, json={'amount': amount})
        if not rows:
            raise FinesError('Satsen blev ikke ændret. Kun administratoren kan ændre satser.')
