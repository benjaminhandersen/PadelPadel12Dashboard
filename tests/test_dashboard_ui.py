import unittest
from unittest.mock import patch
import pandas as pd
from streamlit.testing.v1 import AppTest
from dashboard_ui import render_fixture_cards, render_team_header, render_player_cards


def sample_data():
    matches=pd.DataFrame([
        dict(team_match_id=10,round=1,datetime=pd.Timestamp('2026-10-20 18:00'),opponent='<Modstander>',venue='home',location='Hallen',played=True,our_score=3,their_score=3,won=False),
        dict(team_match_id=20,round=2,datetime=pd.Timestamp('2026-11-01 12:00'),opponent='Næste hold',venue='away',location='Padelcenter',played=False,our_score=None,their_score=None,won=None)])
    individual=pd.DataFrame([dict(team_match_id=10,match_id=100,our_p1_id=1,our_p1_name='Anna',our_p2_id=2,our_p2_name='Bo',opp_p1_name='Carla',opp_p2_name='Dan',won=True,sets_won=2,sets_lost=0,games_won=12,games_lost=6,games_diff=6,sets_str='6-3, 6-3')])
    standings=pd.DataFrame([dict(participant_id=1,team_name='PadelPadel 12',standing=1,played=1,wins=0,draws=1,losses=0,match_points=1,sets_diff=0,games_diff=0)])
    return dict(team_matches=matches,individual=individual,lineup=None,standings=standings,availability={})


class TeamOverviewTests(unittest.TestCase):
    def test_full_dashboard_preserves_tabs_navigation_and_details(self):
        config=dict(active_season='test',seasons={'test':dict(team_id=1,pool_id=1,label='Testsæson')})
        with patch('fines_connection.require_app_login',return_value=None), patch('fines_ui.render_fines'), patch('padel_pipeline.build_dataset',return_value=sample_data()), patch('app_config.load_config',return_value=config):
            app=AppTest.from_file('dashboard.py').run()
        self.assertFalse(app.exception)
        self.assertEqual([t.label for t in app.tabs],['Overblik','Spillere','Makkerpar','Resultater','Kampprogram','Tilgængelighed','Bødekassen'])
        html='\n'.join(m.value for m in app.markdown)
        self.assertIn('Holdoverblik',html)
        self.assertIn('Næste kamp',html)
        self.assertIn('&lt;Modstander&gt;',html)
        self.assertIn('Uafgjort',html)
        self.assertTrue(app.dataframe)

    def test_empty_season_and_missing_results(self):
        app=AppTest.from_string('''
import pandas as pd
from dashboard_ui import render_team_header,render_season_highlights,render_fixture_cards
render_team_header('<Hold>', 'Sæson', None, pd.DataFrame())
render_season_highlights(pd.DataFrame())
render_fixture_cards(pd.DataFrame([dict(datetime=pd.NaT,round=1,opponent='Hold',venue='away',location=None,our_score=None,their_score=None)]),played=True)
''').run()
        self.assertFalse(app.exception)
        self.assertTrue(app.info)
        html='\n'.join(m.value for m in app.markdown)
        self.assertIn('&lt;Hold&gt;',html)
        self.assertIn('Resultat afventer',html)
        self.assertIn('Dato afventer',html)
