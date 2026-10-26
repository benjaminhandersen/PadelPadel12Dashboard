import pandas as pd
import streamlit as st
from uuid import uuid4

from fines_connection import get_store
from supabase_fines import FinesError, SupabaseFines


def render_fines(players=None):
    roster = [p if isinstance(p, dict) else {'name': str(p), 'player_id': None} for p in (players or [])]
    players = sorted({p['name'].strip() for p in roster if p['name'].strip()})
    st.subheader('Bødekassen')
    store = get_store()
    if store is None:
        return
    remote = isinstance(store, SupabaseFines)
    st.caption('Vælg bøde → tryk på spilleren. Ét tryk giver én bøde.')
    if remote:
        st.caption('Fælles bødekasse · gemmes i Supabase')
    else:
        st.info('Lokal udvikling: denne bødekasse deles ikke med onlineappen.')
    st.button('Opdater bødekassen', key='fines_refresh', use_container_width=True)
    st.markdown('''<style>
        .st-key-fines_mobile button {min-height: 54px; white-space: normal;}
        </style>''', unsafe_allow_html=True)

    def notify(message):
        st.session_state['fines_notice'] = message

    def give(player, reason, player_id=None):
        pending = st.session_state.setdefault('fines_pending', {})
        action = (player_id if remote else player, reason)
        request_id = pending.setdefault(action, str(uuid4()))
        try:
            if remote:
                _, amount = store.give_fine(player, reason, roster, request_id=request_id, player_id=player_id)
            else:
                _, amount = store.give_fine(player, reason, players, request_id=request_id)
        except (FinesError, ValueError) as exc:
            st.session_state['fines_error'] = str(exc)
            return
        pending.pop(action, None)
        notify(f'Gemt: {player} · {reason} · {amount} kr.')

    def cancel(fine_id, value):
        try:
            store.set_cancelled(fine_id, value)
        except FinesError as exc:
            st.session_state['fines_error'] = str(exc)
            return
        notify('Bøden er annulleret.' if value else 'Bøden er gendannet.')

    if message := st.session_state.pop('fines_notice', None):
        st.success(message)
    if message := st.session_state.pop('fines_error', None):
        st.error(message)
    try:
        state = store.snapshot()
        if remote:
            store.sync_roster(roster, state)
    except FinesError as exc:
        st.error(str(exc))
        return
    fines = state['fines']
    # Stable Rankedin IDs join historical snapshots to current display names.
    names = {p['player_id']: p['name'] for p in state.get('players', [])}
    names.update({p['player_id']: p['name'] for p in roster if p['player_id'] is not None})
    for fine in fines:
        fine['player'] = names.get(fine.get('player_id'), fine['player'])
    active = [f for f in fines if not f['cancelled']]
    total = sum(f['amount'] for f in active)
    st.metric('Samlede bøder', f'{total:,} kr.'.replace(',', '.'))
    count = sum(f.get('quantity', 1) for f in active)
    st.caption(f'{count} aktive bøder · beløbet viser tildelte bøder, ikke indbetalinger')
    view = st.radio('Vis', ['Giv bøde', 'Overblik', 'Historik', 'Indstillinger'], horizontal=True, key='fines_view')
    ledger_players = sorted(set(players) | {f['player'] for f in fines})

    if view == 'Giv bøde':
        if not players:
            st.warning('Ingen holdspillere hentet fra Rankedin. Nye bøder kan først tildeles, når spillerlisten er tilgængelig.')
            return
        st.caption('Spillere fra Rankedin for det valgte hold og den valgte sæson.')
        with st.container(key='fines_mobile'):
            reason = st.session_state.get('fines_reason')
            rules = {r['name']: r['amount'] for r in state['rules']}
            if reason not in rules:
                st.markdown('**1 · Vælg bødetype**')
                for name, amount in rules.items():
                    if st.button(f'{name} · {amount} kr. →', key=f'rule_{name}', use_container_width=True):
                        st.session_state['fines_reason'] = name
                        st.rerun()
            else:
                if st.button('← Skift bødetype', use_container_width=True):
                    st.session_state.pop('fines_reason', None)
                    st.rerun()
                st.markdown(f'**{reason} · {rules[reason]} kr.**')
                st.caption('2 · Tryk på spilleren. Vent på kvitteringen før næste bøde.')
                for entry in sorted(roster, key=lambda p: p['name']):
                    player = entry['name']
                    identity = entry['player_id'] if remote else player
                    st.button(f'+ {rules[reason]} kr. · {player}', key=f'fine_{identity}',
                              use_container_width=True, on_click=give, args=(player, reason, entry['player_id']))

    elif view == 'Overblik':
        rows = [{'Spiller': p, 'Antal': sum(f.get('quantity', 1) for f in active if f['player'] == p),
                 'Bøder (kr.)': sum(f['amount'] for f in active if f['player'] == p)} for p in ledger_players]
        table = pd.DataFrame(rows, columns=['Spiller', 'Antal', 'Bøder (kr.)']).sort_values(['Bøder (kr.)', 'Spiller'], ascending=[False, True])
        table.insert(0, 'Plads', table['Bøder (kr.)'].rank(method='min', ascending=False).astype(int))
        st.dataframe(table, hide_index=True, use_container_width=True)
        if not active:
            st.info('Ingen bøder endnu. Start under Giv bøde.')
        else:
            st.markdown('### Hvem har fået hvilke bøder?')
            st.caption('Aktive bøder fordelt på spiller og bødetype. Annullerede bøder vises under Historik.')
            for player in table['Spiller']:
                player_fines = [fine for fine in active if fine['player'] == player]
                with st.container(border=True):
                    player_total = sum(fine['amount'] for fine in player_fines)
                    st.markdown(f'**{player} · {player_total:,} kr.**'.replace(',', '.'))
                    if not player_fines:
                        st.caption('Ingen aktive bøder.')
                        continue
                    reasons = sorted({fine['reason'] for fine in player_fines})
                    for reason in reasons:
                        matching = [fine for fine in player_fines if fine['reason'] == reason]
                        quantity = sum(fine.get('quantity', 1) for fine in matching)
                        amount = sum(fine['amount'] for fine in matching)
                        st.write(f'{quantity} × {reason} · {amount:,} kr.'.replace(',', '.'))
    elif view == 'Historik':
        player_filter = st.selectbox('Spiller', ['Alle'] + ledger_players, key='fines_filter')
        show_cancelled = st.checkbox('Vis annullerede', value=True)
        visible = [f for f in fines if (player_filter == 'Alle' or f['player'] == player_filter)
                   and (show_cancelled or not f['cancelled'])]
        if not visible:
            st.info('Ingen registreringer at vise.')
        limit = st.number_input('Antal registreringer', min_value=10, max_value=1000, value=30, step=10)
        for fine in visible[:limit]:
            with st.container(border=True):
                st.markdown(f"**{fine['player']} · {fine['amount']} kr.**")
                timestamp = pd.Timestamp(fine['created']).tz_convert('Europe/Copenhagen').strftime('%d/%m/%Y %H:%M') if fine['created'] else 'Historisk · dato ukendt'
                st.caption(f"{fine.get('quantity', 1)} × {fine['reason']} · {timestamp}" + (' · ANNULLERET' if fine['cancelled'] else ''))
                st.button('Gendan' if fine['cancelled'] else 'Fortryd bøde', key=f"undo_{fine['id']}",
                          on_click=cancel, args=(fine['id'], not fine['cancelled']), use_container_width=True)
        if fines:
            exported = pd.DataFrame(fines).rename(columns={'created': 'Tidspunkt (UTC)', 'player': 'Spiller',
                'reason': 'Bøde', 'amount': 'Beløb (kr.)', 'cancelled': 'Annulleret'})
            st.download_button('Hent hele historikken (CSV)', exported.to_csv(index=False).encode('utf-8-sig'),
                               'boedekasse.csv', 'text/csv')
    else:
        if remote and state['role'] != 'admin':
            st.info('Kun holdets administrator kan ændre satser.')
            return
        st.caption('Satser gælder kun nye bøder. Tidligere beløb bevares.')
        with st.form('fine_rate_form'):
            rate_name = st.selectbox('Bødetype', [r['name'] for r in state['rules']])
            new_amount = st.number_input('Ny sats (kr.)', min_value=1, max_value=10000, value=10, step=1)
            if st.form_submit_button('Gem sats'):
                try:
                    store.update_rate(rate_name, int(new_amount))
                except FinesError as exc:
                    st.error(str(exc))
                else:
                    notify(f'Satsen for {rate_name} er gemt: {new_amount} kr.')
                    st.rerun()
        st.dataframe(pd.DataFrame(state['rules']).rename(columns={'name': 'Bødetype', 'amount': 'Sats (kr.)'}),
                     hide_index=True, use_container_width=True)
        st.caption('Spillerlisten styres af holddata fra Rankedin og kan ikke redigeres her.')
