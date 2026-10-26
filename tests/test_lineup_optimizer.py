import unittest
from copy import deepcopy
import pandas as pd
from lineup_optimizer import player_history, pair_history, pair_strengths, suggest_two_round_lineups
from padel_pipeline import parse_individual_matches
from tests import test_rankedin_parsers as parser_fixtures


def match(a, b, court=2, won=True, diff=4):
    return dict(our_p1_id=a, our_p1_name=f'P{a}', our_p2_id=b, our_p2_name=f'P{b}',
                court=court, won=won, games_diff=diff)


class StrengthTests(unittest.TestCase):
    def test_court_one_win_counts_more_than_court_three(self):
        df=pd.DataFrame([match(1,2,1),match(3,4,3)])
        players=player_history(df).set_index('player_id')
        pairs=pair_strengths(range(1,5),df)
        self.assertGreater(players.loc[1,'player_score'],players.loc[3,'player_score'])
        self.assertGreater(pairs[(1,2)],pairs[(3,4)])

    def test_new_strong_pair_can_outrank_established_pair(self):
        df=pd.DataFrame([match(1,3,1),match(2,4,1),match(5,6,3)])
        scores=pair_strengths(range(1,7),df)
        players=player_history(df).set_index('player_id')
        self.assertEqual(scores[(1,2)],(players.loc[1,'player_score']+players.loc[2,'player_score'])/2)
        self.assertGreater(scores[(1,2)],scores[(5,6)])
        self.assertEqual(pair_strengths([7,8],df)[(7,8)],50)

    def test_strength_order_and_valid_lineups_in_every_proposal(self):
        df=pd.DataFrame([match(5,6,1),match(3,4,2),match(1,2,3,False,-5)])
        players=pd.DataFrame({'player_id':range(1,7),'name':[f'P{i}' for i in range(1,7)]})
        result=suggest_two_round_lineups(range(1,7),players,df,20)
        for _, row in result.iterrows():
            all_pairs=[]
            for r in (1,2):
                scores=[row[f'Round {r} - Par {i} score'] for i in (1,2,3)]
                self.assertEqual(scores,sorted(scores,reverse=True))
                pairs=[row[f'Round {r} - Par {i}'] for i in (1,2,3)]
                all_pairs.extend(pairs)
                self.assertEqual(len(set(' & '.join(pairs).split(' & '))),6)
            self.assertEqual(len(set(all_pairs)),6)

    def test_missing_court_is_neutral_and_small_samples_smoothed(self):
        df=pd.DataFrame([match(1,2)]).drop(columns='court')
        score=player_history(df).iloc[0]['player_score']
        self.assertAlmostEqual(score,68,places=2)
        self.assertTrue(pair_history(df)['pair_score'].notna().all())

    def test_parser_preserves_slots_and_excludes_decider(self):
        fixture=parser_fixtures.RankedinParserTests();fixture.setUp()
        raw=deepcopy(fixture.details)
        raw[0]['Settings']={'MatchOrder':1}
        raw[0]['Matches']['Matches']=[deepcopy(raw[0]['Matches']['Matches'][0]) for _ in range(7)]
        raw[0]['Matches']['Matches'][1]['MatchResult']['HasScore']=False
        for value in (raw,parser_fixtures.camelize(raw)):
            rows=parse_individual_matches(value,1,True)
            self.assertEqual([r['court'] for r in rows],[1,3,1,2,3,None])
        raw[0]['Settings']['MatchOrder']=99
        self.assertTrue(all(r['court'] is None for r in parse_individual_matches(raw,1,True)))
