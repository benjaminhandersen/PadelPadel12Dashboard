"""Shared season polls. All requests run on the authenticated Python server."""
from datetime import datetime
from uuid import UUID, uuid5

from supabase_fines import FinesError


def make_slots(poll_id, values):
    """Stable IDs preserve answers for unchanged times; changed times need new answers."""
    starts = sorted({datetime.fromisoformat(str(value)).replace(second=0, microsecond=0).isoformat(timespec='minutes') for value in values})
    if not 1 <= len(starts) <= 100:
        raise FinesError('Tilføj mellem 1 og 100 tidspunkter.')
    return [dict(id=str(uuid5(UUID(poll_id), value)), starts_at=value) for value in starts]


class PlanningStore:
    def __init__(self, backend):
        # Reuse the already authenticated client's request interface. Streamlit
        # reloads can retain a client created from an earlier class definition;
        # Python class identity is neither an authorization check nor a reliable
        # way to detect a working connection. request() and DB grants enforce access.
        if not callable(getattr(backend, 'request', None)):
            raise FinesError('Kampplanlægning mangler en fælles databaseforbindelse. Log ud og ind igen, eller kontakt administratoren.')
        self.backend = backend

    def snapshot(self, season):
        return self.backend.request('POST', '/rest/v1/rpc/padel_planning_snapshot', json={'p_season': season})

    def save_poll(self, poll):
        return self.backend.request('POST', '/rest/v1/rpc/padel_planning_save_poll', json={
            'p_id': poll['id'], 'p_season': poll['season_key'], 'p_title': poll['title'].strip(),
            'p_slots': poll['slots'], 'p_deadline': poll.get('deadline'),
            'p_status': poll.get('status', 'open'), 'p_final_slot': poll.get('final_slot'),
            'p_version': poll.get('version', 0)})

    def save_vote(self, poll, player_id, selected, version=0):
        ids = {s['id'] for s in poll['slots']}
        if not set(selected) <= ids:
            raise FinesError('Forslaget er ændret. Hent seneste svar og prøv igen.')
        return self.backend.request('POST', '/rest/v1/rpc/padel_planning_save_vote', json={
            'p_poll': poll['id'], 'p_player': int(player_id),
            'p_answers': {slot_id: slot_id in selected for slot_id in ids},
            'p_poll_version': poll['version'], 'p_version': version})


def slot_summary(poll, votes, players):
    rows = []
    for slot in poll['slots']:
        yes, no, pending = [], [], []
        for player in players:
            vote = next((v for v in votes if v['poll_id'] == poll['id'] and v['player_id'] == player['player_id']), {})
            answer = vote.get('answers', {}).get(slot['id'])
            (yes if answer is True else no if answer is False else pending).append(player['name'])
        rows.append(dict(slot=slot, yes=yes, no=no, pending=pending))
    return rows
