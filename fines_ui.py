import pandas as pd
import streamlit as st

import fines_store as store


def render_fines():
    st.subheader('Bødekassen')
    st.caption('Vælg bøde → tryk på spilleren. Ét tryk giver én bøde.')
    st.info('Bøder gemmes på denne server. På Streamlit Cloud kræves ekstern database for varig lagring. Startsaldo er 0 kr.; arkets historik er ikke importeret.')
    st.markdown('''<style>
        .st-key-fines_mobile button {min-height: 54px; white-space: normal;}
        </style>''', unsafe_allow_html=True)

    def notify(message):
        st.session_state['fines_notice'] = message

    def give(player, reason):
        _, amount = store.give_fine(player, reason)
        notify(f'Gemt: {player} · {reason} · {amount} kr.')

    def cancel(fine_id, value):
        store.set_cancelled(fine_id, value)
        notify('Bøden er annulleret.' if value else 'Bøden er gendannet.')

    if message := st.session_state.pop('fines_notice', None):
        st.success(message)
    state = store.snapshot()
    fines = state['fines']
    active = [f for f in fines if not f['cancelled']]
    total = sum(f['amount'] for f in active)
    st.metric('Samlede bøder', f'{total:,} kr.'.replace(',', '.'))
    st.caption(f'{len(active)} aktive bøder · beløbet viser tildelte bøder, ikke indbetalinger')
    view = st.radio('Vis', ['Giv bøde', 'Overblik', 'Historik', 'Indstillinger'], horizontal=True, key='fines_view')
    players = [p['name'] for p in state['players']]

    if view == 'Giv bøde':
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
                for player in players:
                    st.button(f'+ {rules[reason]} kr. · {player}', key=f'fine_{player}',
                              use_container_width=True, on_click=give, args=(player, reason))

    elif view == 'Overblik':
        rows = [{'Spiller': p, 'Antal': sum(f['player'] == p for f in active),
                 'Bøder (kr.)': sum(f['amount'] for f in active if f['player'] == p)} for p in players]
        table = pd.DataFrame(rows).sort_values(['Bøder (kr.)', 'Spiller'], ascending=[False, True])
        table.insert(0, 'Plads', table['Bøder (kr.)'].rank(method='min', ascending=False).astype(int))
        st.dataframe(table, hide_index=True, use_container_width=True)
        if not active:
            st.info('Ingen bøder endnu. Start under Giv bøde.')
    elif view == 'Historik':
        player_filter = st.selectbox('Spiller', ['Alle'] + players, key='fines_filter')
        show_cancelled = st.checkbox('Vis annullerede', value=True)
        visible = [f for f in fines if (player_filter == 'Alle' or f['player'] == player_filter)
                   and (show_cancelled or not f['cancelled'])]
        if not visible:
            st.info('Ingen registreringer at vise.')
        limit = st.number_input('Antal registreringer', min_value=10, max_value=1000, value=30, step=10)
        for fine in visible[:limit]:
            with st.container(border=True):
                st.markdown(f"**{fine['player']} · {fine['amount']} kr.**")
                timestamp = pd.Timestamp(fine['created']).tz_convert('Europe/Copenhagen').strftime('%d/%m/%Y %H:%M')
                st.caption(f"{fine['reason']} · {timestamp}" + (' · ANNULLERET' if fine['cancelled'] else ''))
                st.button('Gendan' if fine['cancelled'] else 'Fortryd bøde', key=f"undo_{fine['id']}",
                          on_click=cancel, args=(fine['id'], not fine['cancelled']), use_container_width=True)
        if fines:
            exported = pd.DataFrame(fines).rename(columns={'created': 'Tidspunkt (UTC)', 'player': 'Spiller',
                'reason': 'Bøde', 'amount': 'Beløb (kr.)', 'cancelled': 'Annulleret'})
            st.download_button('Hent hele historikken (CSV)', exported.to_csv(index=False).encode('utf-8-sig'),
                               'boedekasse.csv', 'text/csv')
    else:
        st.caption('Satser gælder kun nye bøder. Tidligere beløb bevares.')
        with st.form('fine_rate_form'):
            rate_name = st.selectbox('Bødetype', [r['name'] for r in state['rules']])
            new_amount = st.number_input('Ny sats (kr.)', min_value=1, max_value=10000, value=10, step=1)
            if st.form_submit_button('Gem sats'):
                store.update_rate(rate_name, int(new_amount))
                notify(f'Satsen for {rate_name} er gemt: {new_amount} kr.')
                st.rerun()
        st.dataframe(pd.DataFrame(state['rules']).rename(columns={'name': 'Bødetype', 'amount': 'Sats (kr.)'}),
                     hide_index=True, use_container_width=True)
        with st.form('fine_player_form', clear_on_submit=True):
            name = st.text_input('Ny spiller', max_chars=80)
            if st.form_submit_button('Tilføj spiller'):
                try:
                    store.add_player(name)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    notify(f'{name.strip()} er tilføjet.')
                    st.rerun()
