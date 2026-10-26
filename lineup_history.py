"""Load team history across every configured season for lineup assessment."""
import pandas as pd
from padel_pipeline import fetch, url_team_matches, url_team_match_details, parse_team_matches, parse_individual_matches


def load_lineup_history(seasons):
    rows, warnings, loaded = [], [], []
    for key, season in seasons.items():
        label = season.get('label', key)
        try:
            team_id = int(season['team_id'])
            matches = parse_team_matches(fetch(url_team_matches(team_id), cache_key=f'team_matches_{team_id}'), team_id)
        except Exception:
            warnings.append(f'{label}: sæsonens kampe kunne ikke hentes.')
            continue
        loaded.append(label)
        for _, match in matches[matches['played']].iterrows():
            match_id = int(match['team_match_id'])
            try:
                raw = fetch(url_team_match_details(match_id), cache_key=f'match_details_{match_id}')
                rows.extend(parse_individual_matches(raw, match_id, match['we_are_challenger']))
            except Exception:
                warnings.append(f'{label}: historik for holdkamp {match_id} kunne ikke hentes.')
    history = pd.DataFrame(rows)
    if not history.empty:
        # A season may be configured twice; never count a match twice.
        history = history.drop_duplicates(subset=['team_match_id', 'match_id']).reset_index(drop=True)
    return history, loaded, warnings
