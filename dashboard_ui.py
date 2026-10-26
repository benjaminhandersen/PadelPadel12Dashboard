"""Responsive, scoped presentation for the team's season overview."""
from html import escape
import pandas as pd
import streamlit as st

STYLE = '''<style>
.st-key-team-overview-tabs [data-baseweb="tab-highlight"]{background-color:#359578}
.st-key-team-overview-tabs [role="tab"][aria-selected="true"]{color:#359578}
.team-view{font-family:inherit;color:inherit}.team-view *{box-sizing:border-box}
.team-view .tv-hero{background:linear-gradient(120deg,#112b3d,#194b55);color:#fff;border-radius:22px;padding:28px;margin:8px 0 24px}
.team-view .tv-eyebrow{font-size:11px;letter-spacing:2px;font-weight:750;text-transform:uppercase;color:#a9e6d1}
.team-view h1{font-size:32px;color:#fff;margin:10px 0 8px;padding:0;line-height:1.2}
.team-view .tv-subtitle{font-size:14px;color:#d4e5ea;line-height:1.6}
.team-view .tv-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;margin-top:26px}
.team-view .tv-metric{border-left:2px solid #75c5ae;padding-left:14px}
.team-view .tv-metric strong{font-size:28px;display:block;color:white}.team-view .tv-metric span{font-size:12px;color:#d4e5ea}
.team-view .tv-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin:12px 0 22px}
.team-view .tv-pair-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
.team-view .tv-highlights{grid-template-columns:repeat(2,minmax(0,1fr))}
.team-view .tv-card{background:#fff;color:#17283e;border:1px solid #dfe7ec;border-radius:16px;padding:20px;min-width:0;overflow-wrap:anywhere}
.team-view .tv-kicker{color:#436674;font-size:11px;font-weight:750;letter-spacing:1.2px;text-transform:uppercase}
.team-view .tv-card h3{color:#17283e;font-size:20px;line-height:1.35;margin:12px 0 8px;padding:0}
.team-view .tv-meta{font-size:12px;color:#526678;line-height:1.65}
.team-view .tv-form{display:flex;gap:6px;flex-wrap:wrap;margin:16px 0}
.team-view .tv-badge{display:inline-flex;align-items:center;justify-content:center;border-radius:8px;padding:6px 9px;font-size:12px;font-weight:750;background:#edf1f5;color:#465568}
.team-view .tv-win{background:#e3f4ec;color:#176647}.team-view .tv-loss{background:#fcebec;color:#a23c49}.team-view .tv-draw{background:#fff3d7;color:#88631d}
.team-view .tv-section{font-size:20px;font-weight:750;margin:20px 0 6px}
.team-view .tv-standing{display:grid;grid-template-columns:38px minmax(0,1fr) 84px 64px;gap:12px;align-items:center;background:#fff;color:#17283e;border:1px solid #dfe7ec;padding:14px 16px;margin:8px 0;border-radius:12px}
.team-view .tv-standing.tv-us{background:#e7f4ee;border-color:#6eb298;border-left:4px solid #217554}
.team-view .tv-rank{font-size:18px;font-weight:800;color:#2d6d58}.team-view .tv-team{font-size:14px;font-weight:700;overflow-wrap:anywhere}
.team-view .tv-small{font-size:11px;color:#526678;line-height:1.5}.team-view .tv-points{text-align:right;font-size:20px;font-weight:800}.team-view .tv-points small{display:block;font-size:10px;font-weight:500;color:#526678}
.team-view .tv-person{display:flex;gap:12px;align-items:center;margin-bottom:16px}.team-view .tv-avatar{width:40px;height:40px;border-radius:12px;display:grid;place-items:center;flex-shrink:0;background:#e4f4ed;color:#176647;font-size:12px;font-weight:800}
.team-view .tv-person strong{font-size:16px;overflow-wrap:anywhere}.team-view .tv-numbers{display:flex;justify-content:space-between;gap:10px;font-size:12px;margin-top:14px;color:#526678}.team-view .tv-numbers b{font-size:20px;display:block;color:#17283e}
.team-view .tv-period{border-top:1px solid #dfe7ec;padding-top:10px;margin-top:10px;display:flex;justify-content:space-between;gap:8px;font-size:11px;line-height:1.6;flex-wrap:wrap}.team-view .tv-period strong{color:#254b56}.team-view .tv-period span{color:#526678}
.team-view .tv-bar{height:7px;background:#edf1f5;border-radius:8px;overflow:hidden;margin-top:16px}.team-view .tv-bar span{height:100%;background:#359578;display:block}
.team-view .tv-result{font-size:32px;font-weight:800;margin:12px 0;color:#17283e}.team-view .tv-separator{color:#9aabb7;padding:0 7px}
@media(max-width:900px){.team-view .tv-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:600px){.team-view .tv-grid{grid-template-columns:1fr}.team-view .tv-metrics{grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}.team-view .tv-hero{padding:22px}.team-view h1{font-size:27px}.team-view .tv-metric strong{font-size:24px}.team-view .tv-standing{grid-template-columns:24px minmax(0,1fr) 45px;gap:8px;padding:12px}.team-view .tv-standing .tv-record{display:none}.team-view .tv-card{padding:17px}}
</style>'''


def _text(value, default='—'):
    return default if value is None or pd.isna(value) else escape(str(value))


def _number(value, signed=False):
    if value is None or pd.isna(value):
        return '—'
    return f'{int(value):+d}' if signed else str(int(value))


def _render(html):
    st.markdown('<div class="team-view">'+html+'</div>', unsafe_allow_html=True)


def render_team_header(name, season, standings_row, matches):
    st.markdown(STYLE, unsafe_allow_html=True)
    played = matches[matches['played']] if not matches.empty else pd.DataFrame()
    if standings_row is not None:
        s=standings_row
        values=[('Placering',f'{_number(s["standing"])}.'),('Holdkampe',f'{_number(s["played"])} / {len(matches)}'),
                ('Point',_number(s['match_points'])),('Partiforskel',_number(s['games_diff'],True))]
    else:
        values=[('Placering','—'),('Holdkampe',f'{len(played)} / {len(matches)}'),('Point','—'),('Partiforskel','—')]
    metrics=''.join(f'<div class="tv-metric"><strong>{value}</strong><span>{label}</span></div>' for label,value in values)
    _render('<section class="tv-hero"><div class="tv-eyebrow">Holdoverblik · PadelPadel 12</div>'
            f'<h1>{_text(name)}</h1><div class="tv-subtitle">{_text(season)} · Statistik for den valgte sæson</div>'
            f'<div class="tv-metrics">{metrics}</div></section>')


def _fixture_card(row, label, played=False):
    dt=pd.to_datetime(row['datetime'])
    date='Dato afventer' if pd.isna(dt) else dt.strftime('%d.%m.%Y · kl. %H:%M')
    venue='Hjemme' if row['venue']=='home' else 'Ude'
    result=''
    if played:
        ours,theirs=row.get('our_score'),row.get('their_score')
        if pd.notna(ours) and pd.notna(theirs):
            outcome,css=('Vundet','tv-win') if ours>theirs else (('Uafgjort','tv-draw') if ours==theirs else ('Tabt','tv-loss'))
            result=f'<div class="tv-result">{_number(ours)}<span class="tv-separator">–</span>{_number(theirs)}</div><span class="tv-badge {css}">{outcome}</span>'
        else:
            result='<div class="tv-meta">Resultat afventer</div>'
    return (f'<article class="tv-card"><div class="tv-kicker">{escape(label)} · Runde {_number(row["round"])}</div>'
            f'<h3>{_text(row["opponent"])}</h3>{result}<div class="tv-meta">{date} · {venue}<br>'
            f'{_text(row.get("location"), "Spillested ikke oplyst")}</div></article>')


def render_season_highlights(matches):
    if matches.empty:
        st.info('Der er ingen kampe i denne sæson endnu.')
        return
    played=matches[matches['played']].sort_values('datetime')
    upcoming=matches[~matches['played']].sort_values('datetime')
    cards=[]
    if not upcoming.empty:
        cards.append(_fixture_card(upcoming.iloc[0],'Næste kamp'))
    else:
        cards.append('<article class="tv-card"><div class="tv-kicker">Kampprogram</div><h3>Alle kampe er spillet</h3><div class="tv-meta">Der er ingen kommende kampe i denne sæson.</div></article>')
    badges=[]
    for _,r in played.tail(5).iterrows():
        a,b=r.get('our_score'),r.get('their_score')
        if pd.isna(a) or pd.isna(b):
            badges.append('<span class="tv-badge">?</span>')
            continue
        letter,css=('V','tv-win') if a>b else (('U','tv-draw') if a==b else ('T','tv-loss'))
        badges.append(f'<span class="tv-badge {css}" title="{_text(r["opponent"])}: {_number(a)}–{_number(b)}">{letter}</span>')
    cards.append('<article class="tv-card"><div class="tv-kicker">Holdets form</div><h3>Seneste fem holdkampe</h3>'
                 f'<div class="tv-form">{"".join(badges) if badges else "Ingen resultater endnu"}</div>'
                 '<div class="tv-meta">Ældste til venstre · nyeste til højre<br>V = vundet · U = uafgjort · T = tabt</div></article>')
    _render('<div class="tv-grid tv-highlights">'+''.join(cards)+'</div>')


def render_standings(standings, our_id):
    rows=[]
    for _,r in standings.sort_values('standing').iterrows():
        css=' tv-us' if r['participant_id']==our_id else ''
        rows.append(f'<div class="tv-standing{css}"><div class="tv-rank">{_number(r["standing"])}</div>'
                    f'<div><div class="tv-team">{_text(r["team_name"])}</div><div class="tv-small">{_number(r["played"])} kampe · Partier {_number(r["games_diff"],True)}</div></div>'
                    f'<div class="tv-small tv-record">{_number(r["wins"])} V · {_number(r["draws"])} U · {_number(r["losses"])} T</div>'
                    f'<div class="tv-points">{_number(r["match_points"])}<small>POINT</small></div></div>')
    _render(''.join(rows))


def render_player_cards(stats):
    cards=[]
    for _,r in stats.iterrows():
        name=str(r['Spiller'])
        initials=''.join(p[0] for p in name.split()[:2]).upper()
        pct=float(r['Match %'])
        cards.append('<article class="tv-card"><div class="tv-person">'
                     f'<span class="tv-avatar">{escape(initials)}</span><strong>{escape(name)}</strong></div>'
                     f'<div class="tv-numbers"><span><b>{_number(r["Ind. kampe"])}</b>Kampe</span><span><b>{_number(r["Match V"])}</b>Sejre</span><span><b>{pct:g} %</b>Vundet</span></div>'
                     f'<div class="tv-bar"><span style="width:{max(0,min(100,pct))}%"></span></div>'
                     f'<div class="tv-meta" style="margin-top:12px">Sæt {_number(r["Sæt±"],True)} · Partier {_number(r["Partier±"],True)}</div></article>')
    _render('<div class="tv-grid">'+''.join(cards)+'</div>')


def render_pair_cards(pairs):
    cards=[]
    for index,(_,r) in enumerate(pairs.iterrows(),1):
        pct=float(r['win_pct'])
        periods=[]
        for prefix, label in (('previous','Tidligere sæsoner'), ('current','Indeværende sæson')):
            played=int(r.get(f'{prefix}_played',0))
            wins=int(r.get(f'{prefix}_wins',0))
            losses=int(r.get(f'{prefix}_losses',0))
            percentage=float(r.get(f'{prefix}_win_pct',0))
            summary=(f'{played} {"kamp" if played == 1 else "kampe"} · {wins} V / {losses} T · {percentage:g} %' if played else 'Ingen kampe sammen')
            periods.append(f'<div class="tv-period"><strong>{label}</strong><span>{summary}</span></div>')
        cards.append(f'<article class="tv-card"><div class="tv-kicker">Makkerpar · #{index}</div><h3>{_text(r["pair_name"])}</h3>'
                     f'<div class="tv-numbers"><span><b>{_number(r["played"])}</b>Kampe sammen</span><span><b>{_number(r["wins"])}</b>Sejre</span><span><b>{pct:g} %</b>Vundet</span></div>'
                     f'<div class="tv-bar"><span style="width:{max(0,min(100,pct))}%"></span></div>' + ''.join(periods) + '</article>')
    _render('<div class="tv-grid tv-pair-grid">'+''.join(cards)+'</div>')


def render_fixture_cards(matches, played=False):
    _render('<div class="tv-grid tv-highlights">'+''.join(_fixture_card(r,'Resultat' if played else 'Kommende kamp',played) for _,r in matches.iterrows())+'</div>')
