"""Mobile-friendly date proposals and shared player availability."""
import calendar
from datetime import date, datetime, timedelta
from uuid import uuid4

import pandas as pd
import streamlit as st

from planning_store import PlanningStore, make_slots, slot_summary
from supabase_fines import FinesError


def today():
    return pd.Timestamp.now(tz='Europe/Copenhagen').date()


def time_label(slot):
    value = datetime.fromisoformat(slot['starts_at'])
    weekdays = ['Mandag', 'Tirsdag', 'Onsdag', 'Torsdag', 'Fredag', 'Lørdag', 'Søndag']
    return f"{weekdays[value.weekday()]} {value:%d/%m/%Y} kl. {value:%H.%M}"


def receipt(message):
    st.session_state['planning_receipt'] = message
    st.rerun()


def mutation_error():
    st.error('Kunne ikke gemme. Forslaget eller svaret kan være ændret af en anden, eller svarfristen er udløbet. Hent seneste svar og prøv igen.')


MONTHS = ['Januar', 'Februar', 'Marts', 'April', 'Maj', 'Juni',
          'Juli', 'August', 'September', 'Oktober', 'November', 'December']


def shift_month(key, direction):
    current = date.fromisoformat(st.session_state[key])
    month_index = current.year * 12 + current.month - 1 + direction
    st.session_state[key] = date(month_index // 12, month_index % 12 + 1, 1).isoformat()


def toggle_day(key, value):
    selected = set(st.session_state[key])
    if value in selected:
        selected.remove(value)
    else:
        selected.add(value)
    st.session_state[key] = sorted(selected)


def render_calendar(prefix, initial_days):
    days_key, month_key = prefix + '_days', prefix + '_month'
    selected = st.session_state.setdefault(days_key, list(initial_days))
    start = date.fromisoformat(initial_days[0]) if initial_days else today()
    st.session_state.setdefault(month_key, start.replace(day=1).isoformat())
    month = date.fromisoformat(st.session_state[month_key])
    with st.container(key=prefix + '_calendar', border=True):
        st.markdown('''<style>
        [class*="planning_edit_"][class*="_calendar"] [data-testid="stHorizontalBlock"] {
            flex-direction:row!important; flex-wrap:nowrap!important; gap:4px;
        }
        [class*="planning_edit_"][class*="_calendar"] [data-testid="stColumn"] {
            min-width:0!important; flex:1 1 0!important; width:0!important;
        }
        [class*="planning_edit_"][class*="_calendar"] button {
            padding:0.25rem!important; min-height:42px;
        }
        [class*="planning_edit_"][class*="_calendar"] button p {font-size:14px;}
        </style>''', unsafe_allow_html=True)
        prev, heading, following = st.columns([1, 5, 1])
        with prev:
            st.button('‹', key=prefix + '_prev', help='Forrige måned',
                      on_click=shift_month, args=(month_key, -1), use_container_width=True)
        with heading:
            st.markdown(f'**{MONTHS[month.month - 1]} {month.year}**')
        with following:
            st.button('›', key=prefix + '_next', help='Næste måned',
                      on_click=shift_month, args=(month_key, 1), use_container_width=True)
        for col, label in zip(st.columns(7), ['Ma', 'Ti', 'On', 'To', 'Fr', 'Lø', 'Sø']):
            col.caption(label)
        for week in calendar.monthcalendar(month.year, month.month):
            for col, number in zip(st.columns(7), week):
                if number:
                    value = month.replace(day=number).isoformat()
                    col.button(str(number), key=prefix + '_date_' + value,
                               type='primary' if value in selected else 'secondary',
                               help=f'{number}. {MONTHS[month.month - 1].lower()} {month.year}',
                               on_click=toggle_day, args=(days_key, value), use_container_width=True)
                else:
                    col.write(' ')
    return list(selected)


def render_editor(store, season, poll=None):
    token = f"{poll['id']}_{poll['version']}" if poll else st.session_state.setdefault('planning_new_id', str(uuid4()))
    poll_id = poll['id'] if poll else token
    prefix = f'planning_edit_{token}'
    initial = {}
    for slot in poll['slots'] if poll else []:
        value = datetime.fromisoformat(slot['starts_at'])
        initial.setdefault(value.date().isoformat(), []).append(value.strftime('%H:%M'))
    title = st.text_input('Navn på forslag / modstander', value=poll['title'] if poll else '',
                          max_chars=150, key=prefix + '_title')
    st.markdown('**1. Vælg dage i kalenderen**')
    st.caption('Tryk på alle de dage, du vil foreslå. Tryk igen for at fjerne en dag. Du kan vælge på tværs af måneder.')
    selected_days = render_calendar(prefix, sorted(initial))
    st.markdown(f'**2. Tilføj tidspunkter · {len(selected_days)} valgte dage**')
    if not selected_days:
        st.info('Vælg en eller flere dage i kalenderen ovenfor.')
    chosen = []
    for day in selected_days:
        with st.container(border=True):
            label = time_label({'starts_at': day + 'T00:00'}).split(' kl.')[0]
            st.markdown(f'**{label}**')
            times = sorted(set([f'{hour:02}:{minute:02}' for hour in range(24) for minute in (0, 30)] + initial.get(day, [])))
            hours = st.multiselect('Tidspunkter', times, default=initial.get(day, ['20:00']), key=prefix + '_times_' + day)
            chosen.extend(f'{day}T{hour}' for hour in hours)
    st.caption('Svar på uændrede tidspunkter bevares. Nye tidspunkter skal besvares.')
    use_deadline = st.checkbox('Sæt svarfrist', value=bool(poll and poll.get('deadline')), key=prefix + '_use_deadline')
    deadline = st.date_input('Sidste svardag', value=date.fromisoformat(poll['deadline']) if poll and poll.get('deadline') else today() + timedelta(days=7), key=prefix + '_deadline')
    if st.button('Gem ændringer' if poll else 'Udgiv datoer', key=prefix + '_save', use_container_width=True):
        missing_times = [day for day in selected_days if not any(value.startswith(day + 'T') for value in chosen)]
        if not title.strip() or not selected_days:
            st.error('Udfyld et navn og vælg mindst én dag i kalenderen.')
        elif missing_times:
            st.error('Tilføj mindst ét tidspunkt til hver valgt dag.')
        else:
            try:
                updated = dict(poll or {'status': 'open', 'final_slot': None}, id=poll_id, season_key=season, title=title,
                               slots=make_slots(poll_id, chosen), deadline=str(deadline) if use_deadline else None)
                if updated.get('final_slot') and updated['final_slot'] not in {s['id'] for s in updated['slots']}:
                    st.error('Genåbn forslaget, før du fjerner den fastlagte kampdato.')
                else:
                    store.save_poll(updated)
                    if not poll:
                        st.session_state.pop('planning_new_id', None)
                        st.session_state['planning_show_create'] = False
                    receipt('Forslaget er gemt. Holdet kan nu se datoerne.')
            except FinesError:
                mutation_error()


def render_votes(store, poll, votes, players):
    st.subheader('Dine svar')
    player_map = {p['player_id']: p['name'] for p in players}
    if not player_map:
        st.info('Der er endnu ingen spillere i holdets fælles spillerliste.')
        return
    player_id = st.selectbox('Vælg dit navn', list(player_map), index=None,
                            placeholder='Vælg spiller', format_func=player_map.get, key='planning_player')
    if player_id is None:
        return
    vote = next((v for v in votes if v['poll_id'] == poll['id'] and v['player_id'] == player_id), {})
    closed = poll['status'] != 'open' or bool(poll.get('deadline') and date.fromisoformat(poll['deadline']) < today())
    if closed:
        st.info('Der er lukket for svar på dette forslag.')
    answers = vote.get('answers', {})
    if vote and any(s['id'] not in answers for s in poll['slots']):
        st.warning('Der er tilføjet nye tidspunkter, siden spilleren sidst svarede.')
    prefix = f"planning_vote_{poll['id']}_{poll['version']}_{player_id}_{vote.get('version', 0)}"
    with st.form(prefix):
        st.caption('Sæt kryds ved alle de tidspunkter, du kan. Tidspunkter uden kryds gemmes som “Kan ikke”. Alle på holdet kan rette hinandens svar.')
        selected = [s['id'] for s in poll['slots'] if st.checkbox(time_label(s), value=answers.get(s['id'], False), key=prefix + s['id'], disabled=closed)]
        none = st.checkbox('Jeg kan ingen af tidspunkterne', value=bool(vote) and not any(answers.get(s['id']) for s in poll['slots']), disabled=closed)
        if st.form_submit_button('Gem mine svar', use_container_width=True, disabled=closed):
            if none and selected:
                st.error('Fjern krydset i “Jeg kan ingen”, eller fjern de valgte tidspunkter.')
            elif not selected and not none:
                st.error('Vælg tidspunkter, eller markér “Jeg kan ingen af tidspunkterne”.')
            else:
                try:
                    store.save_vote(poll, player_id, selected, vote.get('version', 0))
                    receipt(f"Svarene for {player_map[player_id]} er gemt.")
                except FinesError:
                    mutation_error()


def render_summary(poll, votes, players):
    st.subheader('Hvem kan spille?')
    for row in slot_summary(poll, votes, players):
        final = row['slot']['id'] == poll.get('final_slot')
        label = f"{'📌 ' if final else ''}{time_label(row['slot'])} · {len(row['yes'])} kan spille"
        with st.container(border=True):
            st.markdown(f'**{label}**')
            if final:
                st.success('Fastlagt kampdato')
            elif len(row['yes']) >= 6:
                st.success('Mindst 6 spillere kan spille')
            st.write('Kan: ' + (', '.join(row['yes']) or 'Ingen endnu'))
            with st.expander(f"Kan ikke: {len(row['no'])} · Mangler svar: {len(row['pending'])}"):
                st.write('Kan ikke: ' + (', '.join(row['no']) or 'Ingen'))
                st.write('Mangler svar: ' + (', '.join(row['pending']) or 'Ingen'))


def render_management(store, season, poll):
    with st.expander('Rediger datoer og indstillinger'):
        st.caption('Alle med adgang til holdets dashboard kan redigere forslaget.')
        render_editor(store, season, poll)
        labels = {s['id']: time_label(s) for s in poll['slots']}
        final_slot = st.selectbox('Vælg endelig kampdato', list(labels), format_func=labels.get,
                                  key=f"planning_final_{poll['id']}_{poll['version']}")
        if st.button('Fastlæg kampdato', key='planning_finalize', use_container_width=True):
            try:
                store.save_poll(dict(poll, status='final', final_slot=final_slot))
                receipt('Kampdatoen er fastlagt, og svarene er låst.')
            except FinesError:
                mutation_error()
        action = 'Luk for svar' if poll['status'] == 'open' else 'Genåbn for svar'
        if st.button(action, key='planning_toggle', use_container_width=True):
            try:
                store.save_poll(dict(poll, status='closed' if poll['status'] == 'open' else 'open', final_slot=None))
                receipt('Forslaget er opdateret.')
            except FinesError:
                mutation_error()
        if poll['status'] != 'archived' and st.button('Arkivér forslag', key='planning_archive', use_container_width=True):
            try:
                store.save_poll(dict(poll, status='archived', final_slot=None))
                receipt('Forslaget er arkiveret. Svarene er bevaret.')
            except FinesError:
                mutation_error()


def render_planning(backend, season, season_label):
    st.subheader('Kampplanlægning')
    st.caption(f'{season_label} · Alle tidspunkter er dansk lokal tid.')
    if message := st.session_state.pop('planning_receipt', None):
        st.success(message)
    try:
        store = PlanningStore(backend)
    except FinesError as exc:
        st.error(str(exc))
        return
    if st.button('Opret dato', type='primary', use_container_width=True):
        st.session_state['planning_show_create'] = not st.session_state.get('planning_show_create', False)
    if st.session_state.get('planning_show_create'):
        with st.container(border=True):
            render_editor(store, season)
    st.button('Hent seneste svar', use_container_width=True)
    try:
        state = store.snapshot(season)
    except FinesError:
        st.error('Kunne ikke hente kampforslag fra den fælles database. Prøv “Hent seneste svar” igen. Du kan stadig åbne “Opret dato”.')
        return
    archived = st.checkbox('Vis også arkiverede forslag', key='planning_archived')
    polls = [p for p in state['polls'] if archived or p['status'] != 'archived']
    if not polls:
        st.info('Der er ingen kampforslag endnu. Tryk “Opret dato” for at komme i gang.')
        return
    by_id = {p['id']: p for p in polls}
    status_labels = dict(open='Åben', closed='Lukket', final='Fastlagt', archived='Arkiveret')
    poll_id = st.selectbox('Vælg kampforslag', list(by_id),
                           format_func=lambda key: f"{by_id[key]['title']} · {status_labels[by_id[key]['status']]}")
    poll = by_id[poll_id]
    if poll.get('deadline'):
        st.caption(f"Svarfrist: {date.fromisoformat(poll['deadline']):%d/%m/%Y} kl. 23.59")
    render_votes(store, poll, state['votes'], state['players'])
    render_summary(poll, state['votes'], state['players'])
    render_management(store, season, poll)
