"""Responsive visual overview using the existing ledger snapshots."""
from html import escape

import pandas as pd
import streamlit as st


def kroner(value):
    return f'{value:,} kr.'.replace(',', '.')


def render_overview(active, players, rules):
    types = sorted({r['name'] for r in rules} | {f['reason'] for f in active})
    chosen = st.selectbox('Bødetype', ['Alle bødetyper'] + types, key='fines_overview_type')
    order = st.selectbox('Sortér spillere efter', ['Højeste beløb', 'Flest bøder', 'Navn A–Å'], key='fines_overview_order')
    selected = [f for f in active if chosen == 'Alle bødetyper' or f['reason'] == chosen]
    rows = [{'Spiller': p, 'Antal': sum(f.get('quantity', 1) for f in selected if f['player'] == p),
             'Bøder (kr.)': sum(f['amount'] for f in selected if f['player'] == p)} for p in players]
    table = pd.DataFrame(rows, columns=['Spiller', 'Antal', 'Bøder (kr.)'])
    sort_columns = {'Højeste beløb': (['Bøder (kr.)', 'Antal', 'Spiller'], [False, False, True]),
                    'Flest bøder': (['Antal', 'Bøder (kr.)', 'Spiller'], [False, False, True]),
                    'Navn A–Å': (['Spiller'], [True])}
    columns, ascending = sort_columns[order]
    table = table.sort_values(columns, ascending=ascending)
    # Competition ranks preserve ties, and remain monetary ranks in alphabetical view.
    rank_column = 'Antal' if order == 'Flest bøder' else 'Bøder (kr.)'
    table.insert(0, 'Plads', table[rank_column].rank(method='min', ascending=False).astype(int))
    total = sum(f['amount'] for f in selected)
    count = sum(f.get('quantity', 1) for f in selected)
    involved = sum(row['Antal'] > 0 for row in rows)
    css = '''<style>
    .fine-overview{font-family:inherit;color:inherit}
    .fine-overview *{box-sizing:border-box}
    .fine-overview .fo-hero{background:linear-gradient(125deg,#112b3d,#194b55);color:#fff;border-radius:22px;padding:28px;margin:12px 0 20px}
    .fine-overview .fo-eyebrow{font-size:12px;text-transform:uppercase;letter-spacing:2px;font-weight:700;color:#a9e6d1}
    .fine-overview .fo-total{font-size:clamp(30px,6vw,46px);font-weight:800;line-height:1.2;margin:10px 0 18px}
    .fine-overview .fo-stats{display:flex;gap:28px;flex-wrap:wrap;font-size:14px;color:#d4e5ea}
    .fine-overview .fo-stats strong{font-size:21px;color:white;margin-right:5px}
    .fine-overview .fo-section{font-size:21px;font-weight:750;margin:24px 0 12px}
    .fine-overview .fo-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
    .fine-overview .fo-podium{color:#17283e;background:#fff;border:1px solid #dfe7ec;border-radius:17px;padding:18px;min-width:0}
    .fine-overview .fo-first{background:#fff9e8;border-color:#e8ce83}
    .fine-overview .fo-name{font-weight:700;font-size:16px;overflow-wrap:anywhere;margin:10px 0 4px}
    .fine-overview .fo-money{font-size:25px;font-weight:800}
    .fine-overview .fo-muted{color:#576779;font-size:13px}
    .fine-overview .fo-panel{color:#17283e;background:#fff;border:1px solid #dfe7ec;border-radius:18px;padding:20px;margin:12px 0}
    .fine-overview .fo-card-head{display:flex;gap:12px;align-items:center;margin-bottom:16px}
    .fine-overview .fo-avatar{display:grid;place-items:center;background:#e4f4ed;color:#176647;width:42px;height:42px;border-radius:13px;font-size:14px;font-weight:800;flex-shrink:0}
    .fine-overview .fo-card-head h3{font-size:17px;margin:0;color:#17283e;line-height:1.5}
    .fine-overview .fo-row{display:flex;justify-content:space-between;gap:14px;font-size:14px;margin-top:14px}
    .fine-overview .fo-row span{overflow-wrap:anywhere}
    .fine-overview .fo-row b{white-space:nowrap}
    .fine-overview .fo-track{height:7px;border-radius:20px;background:#edf1f5;margin-top:7px;overflow:hidden}
    .fine-overview .fo-fill{height:100%;border-radius:20px;background:#2d9875}
    .fine-overview .fo-card-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
    .fine-overview .fo-card-grid .fo-panel{margin:0}
    @media(max-width:640px){.fine-overview .fo-grid,.fine-overview .fo-card-grid{grid-template-columns:1fr}.fine-overview .fo-hero{padding:22px}.fine-overview .fo-podium{padding:16px}.fine-overview .fo-stats{gap:16px}}
    </style>'''
    parts = [css, '<div class="fine-overview">',
             f'<div class="fo-hero"><div class="fo-eyebrow">Bødeoverblik · {escape(chosen)}</div>',
             f'<div class="fo-total">{kroner(total)}</div><div class="fo-stats">',
             f'<span><strong>{count}</strong> bøder</span><span><strong>{involved}</strong> spillere med bøder</span>',
             '</div></div>']
    if selected:
        # The podium always shows the leading three, independently of alphabetical card order.
        leaders = table[table['Antal'] > 0].sort_values(
            ['Antal', 'Bøder (kr.)', 'Spiller'] if order == 'Flest bøder' else ['Bøder (kr.)', 'Antal', 'Spiller'],
            ascending=[False, False, True]).head(3)
        parts.append('<div class="fo-section">Toppen af bødekassen</div><div class="fo-grid">')
        for index, (_, row) in enumerate(leaders.iterrows()):
            medal = ['🥇', '🥈', '🥉'][min(int(row['Plads']), 3) - 1]
            parts.append(f'<div class="fo-podium {"fo-first" if row["Plads"] == 1 else ""}">'
                         f'<div>{medal} <span class="fo-muted">Plads {row["Plads"]}</span></div>'
                         f'<div class="fo-name">{escape(row["Spiller"])}</div>'
                         f'<div class="fo-money">{kroner(row["Bøder (kr.)"])}</div>'
                         f'<div class="fo-muted">{row["Antal"]} bøder</div></div>')
        parts.append('</div><div class="fo-section">Fordeling på bødetyper</div><div class="fo-panel">')
        totals = sorted([(reason, sum(f['amount'] for f in selected if f['reason'] == reason))
                         for reason in {f['reason'] for f in selected}], key=lambda r: (-r[1], r[0]))
        for reason, amount in totals:
            quantity = sum(f.get('quantity', 1) for f in selected if f['reason'] == reason)
            parts.append(f'<div class="fo-row"><span>{escape(reason)} · {quantity} bøder</span><b>{kroner(amount)}</b></div>'
                         f'<div class="fo-track"><div class="fo-fill" style="width:{amount / total * 100:.1f}%"></div></div>')
        parts.append('</div>')
    parts.append('<div class="fo-section">Hvem har fået hvilke bøder?</div><div class="fo-card-grid">')
    for _, row in table.iterrows():
        player = row['Spiller']
        player_fines = [fine for fine in selected if fine['player'] == player]
        initials = ''.join(word[0] for word in player.split()[:2]).upper()
        parts.append(f'<div class="fo-panel"><div class="fo-card-head"><div class="fo-avatar">{escape(initials)}</div><div>'
                     f'<h3>{escape(player)} · {kroner(row["Bøder (kr.)"])}</h3>'
                     f'<div class="fo-muted">{row["Antal"]} bøder · plads {row["Plads"]}</div></div></div>')
        if not player_fines:
            parts.append('<div class="fo-muted">Ingen aktive bøder i dette udvalg.</div>')
        else:
            for reason in sorted({fine['reason'] for fine in player_fines}):
                matching = [fine for fine in player_fines if fine['reason'] == reason]
                quantity = sum(fine.get('quantity', 1) for fine in matching)
                amount = sum(fine['amount'] for fine in matching)
                label = escape(f'{quantity} × {reason} · {kroner(amount)}', quote=True)
                parts.append(f'<div class="fo-row" aria-label="{label}"><span>{quantity} × {escape(reason)}</span><b>{kroner(amount)}</b></div>'
                             f'<div class="fo-track"><div class="fo-fill" style="width:{amount / row["Bøder (kr.)"] * 100:.1f}%"></div></div>')
        parts.append('</div>')
    parts.append('</div></div>')
    st.markdown(''.join(parts), unsafe_allow_html=True)
    if not selected:
        st.info('Ingen aktive bøder i det valgte udvalg.')
    st.caption('Kun aktive bøder. Beløb bygger på den sats, som gjaldt ved tildelingen. Annullerede bøder findes under Historik.')
    with st.expander('Vis som tabel'):
        st.dataframe(table, hide_index=True, use_container_width=True)
