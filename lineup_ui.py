"""Mobile-friendly presentation of the optimizer's existing suggestions."""
from html import escape

import streamlit as st


def _rounds_html(row, history_by_pair, selected_names):
    parts = ['<div class="lp-rounds">']
    for round_number in (1, 2):
        playing = set()
        parts.append(f'<div class="lp-round"><div class="lp-round-title"><span class="lp-round-number">{round_number}</span>Runde {round_number}</div>')
        for pair_number in (1, 2, 3):
            names = str(row[f'Round {round_number} - Par {pair_number}']).split(' & ')
            playing.update(names)
            parts.append('<div class="lp-pair"><div class="lp-pair-heading">'
                         f'<div class="lp-label">Bane {pair_number}</div><div class="lp-partners">')
            for name in names:
                initials = ''.join(part[0] for part in name.split()[:2]).upper()
                parts.append(f'<div class="lp-player"><span class="lp-avatar">{escape(initials)}</span><span>{escape(name)}</span></div>')
            parts.append('</div></div><div class="lp-details">')
            pair_history = history_by_pair.get(frozenset(names))
            if pair_history is not None and pair_history['played'] > 0:
                pct = f'{float(pair_history["win_pct"]):g}'.replace('.', ',')
                parts.append(f'<div class="lp-history">{int(pair_history["wins"])} sejre / {int(pair_history["played"])} kampe sammen · <b>{pct} % vundet</b></div>')
                court_counts = ''.join(
                    f'<span>Bane {court}: <b>{int(pair_history.get(f"court_{court}_wins", 0))}/{int(pair_history.get(f"court_{court}_played", 0))}</b></span>'
                    for court in (1, 2, 3))
                parts.append(f'<div class="lp-court-counts">{court_counts}</div>'
                             '<div class="lp-count-caption">Sejre / kampe på hver bane</div>')
            else:
                parts.append('<div class="lp-history lp-new">Har ikke spillet sammen endnu – vurderet ud fra individuelle scores</div>')
            strength = row.get(f'Round {round_number} - Par {pair_number} score')
            if strength is not None:
                parts.append(f'<div class="lp-history">Vurderet styrke: <b>{strength:g}</b></div>')
            parts.append('</div></div>')
        bench = sorted(set(selected_names) - playing)
        label = escape(' · '.join(bench)) if bench else 'Ingen – alle valgte spillere er på banen'
        parts.append(f'<div class="lp-bench"><b>Sidder over:</b> {label}</div></div>')
    parts.append('</div>')
    return ''.join(parts)


def render_lineup_suggestions(results, history, selected_names):
    if results.empty:
        st.info('Ingen forslag til de valgte spillere.')
        return
    options = list(range(len(results)))
    selected = st.selectbox('Vælg holdforslag', options,
                            format_func=lambda i: 'Anbefalet forslag' if i == 0 else f'Alternativ {i} · score {results.iloc[i]["Score"]:g}',
                            key='lineup_proposal')
    row = results.iloc[selected]
    history_by_pair = {frozenset(str(h['pair']).split(' & ')): h for _, h in history.iterrows()}
    styles = '''<style>
    .lineup-view{font-family:inherit;color:inherit}
    .lineup-view *{box-sizing:border-box}
    .lineup-view .lp-hero{background:linear-gradient(125deg,#112b3d,#194b55);color:#fff;border-radius:22px;padding:26px;margin:12px 0 22px}
    .lineup-view .lp-kicker{font-size:12px;letter-spacing:2px;text-transform:uppercase;color:#a9e6d1;font-weight:700}
    .lineup-view .lp-title{font-size:27px;font-weight:800;margin:8px 0}
    .lineup-view .lp-intro{font-size:14px;color:#d4e5ea}
    .lineup-view .lp-stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin-top:22px}
    .lineup-view .lp-stat strong{display:block;font-size:25px;color:white}
    .lineup-view .lp-stat span{font-size:12px;color:#d4e5ea}
    .lineup-view .lp-rounds{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));grid-template-rows:repeat(5,auto);column-gap:18px;row-gap:12px}
    .lineup-view .lp-round{display:grid;grid-template-rows:subgrid;grid-row:span 5;background:#fff;color:#17283e;border:1px solid #dfe7ec;border-radius:20px;padding:20px;min-width:0}
    .lineup-view .lp-round-title{display:flex;gap:10px;align-items:center;font-size:20px;font-weight:800;margin-bottom:16px}
    .lineup-view .lp-round-number{background:#e4f4ed;color:#176647;display:grid;place-items:center;width:34px;height:34px;border-radius:10px}
    .lineup-view .lp-pair{margin:0;border:1px solid #dfe7ec;background:#f4f7fa;border-radius:14px;overflow:hidden}
    .lineup-view .lp-pair-heading{padding:16px 16px 0}
    .lineup-view .lp-partners{display:flex;flex-direction:column;gap:0}
    .lineup-view .lp-details{padding:0 12px 10px}
    .lineup-view .lp-details .lp-history{margin-top:8px;padding-top:6px;border:0}
    .lineup-view .lp-court-counts{display:flex;gap:6px 12px;flex-wrap:wrap;font-size:12px;color:#254b56;margin-top:6px}
    .lineup-view .lp-count-caption{font-size:10px;color:#526678;margin-top:4px}
    .lineup-view .lp-comparison{border:1px solid #dfe7ec;border-radius:14px;padding:14px;margin:0 0 20px;background:#f4f7fa;color:#17283e}
    .lineup-view .lp-comparison .lp-hero{padding:14px 18px;margin:0 0 12px;border-radius:10px;display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
    .lineup-view .lp-comparison .lp-title{font-size:18px;margin:3px 0}
    .lineup-view .lp-comparison .lp-kicker{font-size:10px}
    .lineup-view .lp-comparison .lp-score{text-align:right;font-size:12px;color:#d4e5ea}
    .lineup-view .lp-comparison .lp-score strong{font-size:23px;color:white;display:block}
    .lineup-view .lp-comparison .lp-round{padding:12px;border-radius:10px}
    .lineup-view .lp-comparison .lp-round-title{font-size:16px;margin-bottom:8px}
    .lineup-view .lp-comparison .lp-round-number{width:26px;height:26px}
    .lineup-view .lp-comparison .lp-rounds{row-gap:8px}
    .lineup-view .lp-comparison .lp-pair-heading{padding:10px 12px 0}
    .lineup-view .lp-comparison .lp-player{font-size:13px}
    .lineup-view .lp-comparison .lp-avatar{width:25px;height:25px;font-size:9px}
    .lineup-view .lp-comparison .lp-history{font-size:11px;line-height:1.4}
    .lineup-view .lp-comparison .lp-bench{font-size:11px;margin-top:8px}
    .lineup-view .lp-label{font-size:11px;letter-spacing:1.5px;color:#576779;text-transform:uppercase;font-weight:750;margin-bottom:12px}
    .lineup-view .lp-player{display:flex;align-items:center;gap:10px;font-size:16px;font-weight:700;margin:8px 0;overflow-wrap:anywhere}
    .lineup-view .lp-avatar{display:grid;place-items:center;background:white;border:1px solid #dfe7ec;width:33px;height:33px;border-radius:50%;font-size:11px;font-weight:800;color:#176647;flex-shrink:0}
    .lineup-view .lp-history{font-size:12px;color:#526678;border-top:1px solid #dfe7ec;padding-top:10px;margin-top:12px;line-height:1.6}
    .lineup-view .lp-new{color:#526678}
    .lineup-view .lp-bench{font-size:13px;color:#526678;line-height:1.6;margin-top:16px}
    .lineup-view .lp-section{font-size:21px;font-weight:750;margin:26px 0 12px}
    .lineup-view .lp-workload{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
    .lineup-view .lp-work-card{background:#fff;color:#17283e;border:1px solid #dfe7ec;border-radius:16px;padding:18px;min-width:0}
    .lineup-view .lp-work-card strong{font-size:15px;display:block;margin-bottom:12px}
    .lineup-view .lp-chip{display:inline-block;background:#eaf4ef;color:#1a634b;font-size:12px;border-radius:8px;padding:6px 9px;margin:3px;overflow-wrap:anywhere;max-width:100%}
    .lineup-view .lp-empty{font-size:13px;color:#576779}
    @media(max-width:680px){.lineup-view .lp-rounds,.lineup-view .lp-workload{grid-template-columns:1fr}.lineup-view .lp-rounds{grid-template-rows:none}.lineup-view .lp-round{display:block;grid-row:auto;padding:16px}.lineup-view .lp-pair{margin:12px 0}.lineup-view .lp-hero{padding:20px}.lineup-view .lp-title{font-size:24px}.lineup-view .lp-stats{gap:8px}.lineup-view .lp-stat strong{font-size:22px}}
    </style>'''
    heading = 'Anbefalet opstilling' if selected == 0 else f'Alternativ {selected}'
    parts = [styles, '<div class="lineup-view">',
             f'<div class="lp-hero"><div class="lp-kicker">Holdforslag · {len(selected_names)} spillere valgt</div>'
             f'<div class="lp-title">{heading}</div>'
             '<div class="lp-intro">2 runder · 3 par i hver runde · ingen gentagne makkerpar</div>'
             '<div class="lp-stats">'
             f'<div class="lp-stat"><strong>{row["Score"]:g}</strong><span>Opstillingsscore</span></div>'
             f'<div class="lp-stat"><strong>{int(row["Historiske sejre"])}</strong><span>Sejre med disse par</span></div>'
             f'<div class="lp-stat"><strong>{int(row["Historiske par-kampe"])}</strong><span>Fælles kampe i data</span></div>'
             '</div></div>']
    parts.append(_rounds_html(row, history_by_pair, selected_names))
    parts.append('<div class="lp-section">Fordeling af spilletid</div><div class="lp-workload">')
    for column, label in [('Spiller 2 kampe', 'Spiller begge runder'), ('Spiller 1 kamp', 'Spiller én runde'), ('Spiller 0 kampe', 'Sidder over begge runder')]:
        names = [name.strip() for name in str(row.get(column, '')).split(',') if name.strip()]
        parts.append(f'<div class="lp-work-card"><strong>{label}</strong>')
        parts.extend(f'<span class="lp-chip">{escape(name)}</span>' for name in names)
        if not names:
            parts.append('<span class="lp-empty">Ingen</span>')
        parts.append('</div>')
    parts.append('</div></div>')
    st.markdown(''.join(parts), unsafe_allow_html=True)
    st.caption('Stærkeste vurderede par spiller på bane 1 i hver runde. Styrkeindekset er en vurdering, ikke en vinderchance.')
    with st.expander('Sådan beregnes styrken'):
        st.write('Hver kamp giver 100 ved sejr og 0 ved nederlag, plus partiforskel begrænset til ±10. '
                 'Bane 1 giver +20, bane 2 giver 0 og bane 3 giver −20, også ved nederlag. '
                 'Banen antages ud fra Rankedin-rækkefølgen: 1–3 i første runde og 1–3 i anden. '
                 'En eventuel syvende kamp eller ukendt bane får intet banetillæg. '
                 'Spillerscoren er gennemsnittet med to neutrale kampe på 50 som udgangspunkt. '
                 'Et nyt par får gennemsnittet af de to spillerscores. Fælles resultater blandes med '
                 'individvurderingen, der vægter som fire kampe. Spillere uden historik får 50. '
                 'Opstillingsscoren er summen af de seks parvurderinger plus 5 % af spillerscoren pr. deltagelse. '
                 'Vægtene er heuristiske og bruger alle sæsoner, der er tilføjet dashboardet. Alle sæsoner vægter ens.')
    with st.expander('Sammenlign alle forslag'):
        comparisons = ['<div class="lineup-view">']
        for index, (_, proposal) in enumerate(results.iterrows()):
            title = 'Anbefalet opstilling' if index == 0 else f'Alternativ {index}'
            active = ' · Vises ovenfor' if index == selected else ''
            comparisons.append('<section class="lp-comparison">'
                               '<div class="lp-hero"><div><div class="lp-kicker">'
                               f'Forslag {index + 1}{active}</div><div class="lp-title">{title}</div></div>'
                               f'<div class="lp-score"><strong>{proposal["Score"]:g}</strong>Opstillingsscore</div></div>')
            comparisons.append(_rounds_html(proposal, history_by_pair, selected_names))
            comparisons.append('</section>')
        comparisons.append('</div>')
        st.markdown(''.join(comparisons), unsafe_allow_html=True)
    with st.expander('Se makkerparrenes historik'):
        if history.empty:
            st.info('Ingen makkerpar-historik for de valgte spillere endnu.')
        else:
            labels = {'pair': 'Makkerpar', 'played': 'Kampe', 'wins': 'Vundet', 'losses': 'Tabt',
                      'win_pct': 'Vundet %', 'games_diff': 'Partier±', 'pair_score': 'Vurderet styrke'}
            labels.update({f'court_{court}_{metric}': f'Bane {court} · {label}' for court in (1, 2, 3) for metric, label in (('wins', 'Sejre'), ('played', 'Kampe'))})
            st.dataframe(history.drop(columns=['pair_key'], errors='ignore').rename(columns=labels), use_container_width=True, hide_index=True)
