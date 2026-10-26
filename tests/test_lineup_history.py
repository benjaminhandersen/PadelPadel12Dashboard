import unittest
from unittest.mock import patch
import pandas as pd
from lineup_history import load_lineup_history
from lineup_optimizer import pair_history


class AllSeasonHistoryTests(unittest.TestCase):
    @patch('lineup_history.parse_individual_matches')
    @patch('lineup_history.parse_team_matches')
    @patch('lineup_history.fetch')
    def test_combines_seasons_without_duplicate_matches(self, fetch, parse_team, parse_individual):
        parse_team.side_effect = [pd.DataFrame([dict(team_match_id=i,played=True,we_are_challenger=False)]) for i in (10,20,10)]
        parse_individual.side_effect = [[dict(team_match_id=i,match_id=i+1,our_p1_id=1,our_p2_id=2,
            our_p1_name='Anna',our_p2_name='Bo',won=True,games_diff=4,court=c)] for i,c in ((10,1),(20,3),(10,1))]
        seasons={key:dict(team_id=i,label=key) for key,i in (('spring',1),('autumn',2),('duplicate',1))}
        history, loaded, warnings=load_lineup_history(seasons)
        self.assertEqual(len(history),2)
        self.assertEqual(len(loaded),3)
        self.assertFalse(warnings)
        pair=pair_history(history).iloc[0]
        self.assertEqual(pair['played'],2)
        self.assertEqual(pair['court_1_wins'],1)
        self.assertEqual(pair['court_3_wins'],1)
        self.assertFalse(parse_individual.call_args.args[2])

    @patch('lineup_history.fetch',side_effect=RuntimeError('offline'))
    def test_missing_season_is_visible(self, fetch):
        history, loaded, warnings=load_lineup_history({'old':dict(team_id=1,label='Old season')})
        self.assertTrue(history.empty)
        self.assertFalse(loaded)
        self.assertEqual(len(warnings),1)
        self.assertIn('Old season',warnings[0])

    @patch('lineup_history.parse_team_matches',return_value=pd.DataFrame([dict(team_match_id=10,played=True,we_are_challenger=True)]))
    @patch('lineup_history.fetch',side_effect=[{},RuntimeError('offline')])
    def test_missing_match_is_visible(self, fetch, parse_team):
        history, loaded, warnings=load_lineup_history({'old':dict(team_id=1)})
        self.assertTrue(history.empty)
        self.assertEqual(loaded,['old'])
        self.assertIn('10',warnings[0])


class PairPeriodTests(unittest.TestCase):
    def test_periods_add_up_filter_on_total_and_names_use_ids(self):
        from lineup_history import pair_season_stats
        rows=[dict(team_match_id=team,match_id=i,our_p1_id=a,our_p2_id=b,
                   our_p1_name=name,our_p2_name='Bo',won=won)
              for i,(team,a,b,name,won) in enumerate([
                  (10,1,2,'Old Anna',True),(20,2,1,'Bo',False),
                  (10,3,2,'Carla',True),(20,4,2,'Dan',False)])]
        rows[1]['our_p2_name']='Anna'
        history=pd.DataFrame(rows+[rows[0]])
        players=pd.DataFrame([dict(player_id=1,name='Anna'),dict(player_id=2,name='Bo')])
        pairs=pair_season_stats(history,[20],current_players=players)
        pair=pairs[pairs.pair_key.map(lambda p: p==(1,2))].iloc[0]
        self.assertEqual(pair['pair_name'],'Anna & Bo')
        self.assertEqual(pair['played'],2)
        self.assertEqual(pair['win_pct'],50)
        self.assertEqual(pair['previous_wins'],1)
        self.assertEqual(pair['current_losses'],1)
        for _,r in pairs.iterrows():
            self.assertEqual(r['played'],r['previous_played']+r['current_played'])
            self.assertEqual(r['wins'],r['previous_wins']+r['current_wins'])
        filtered=pair_season_stats(history,[20],min_matches=2)
        self.assertEqual(len(filtered),1)
        self.assertTrue(pair_season_stats(pd.DataFrame(),[20]).empty)
