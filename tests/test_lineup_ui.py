import unittest
from streamlit.testing.v1 import AppTest


class LineupPresentationTests(unittest.TestCase):
    def test_rounds_alternatives_and_unknown_history(self):
        app = AppTest.from_string('''
import pandas as pd
from lineup_optimizer import suggest_two_round_lineups
from lineup_ui import render_lineup_suggestions
players=pd.DataFrame({'player_id':range(1,7),'name':['Anna','Bo','Carla','Dan','Eva','Finn']})
results=suggest_two_round_lineups(range(1,7),players,pd.DataFrame(),max_results=2)
render_lineup_suggestions(results,pd.DataFrame(),players['name'].tolist())
''').run()
        self.assertFalse(app.exception)
        text = '\n'.join(item.value for item in app.markdown)
        self.assertIn('Runde 1', text)
        self.assertIn('Runde 2', text)
        self.assertEqual(text.count('>Bane 1</div>'), 2)
        self.assertEqual(text.count('Vurderet styrke:'), 6)
        self.assertIn('Stærkeste vurderede par', app.caption[0].value)
        self.assertEqual(text.count('Har ikke spillet sammen endnu – vurderet ud fra individuelle scores'), 6)
        self.assertIn('alle valgte spillere er på banen', text)
        app.selectbox[0].set_value(1).run()
        self.assertFalse(app.exception)
        self.assertIn('Alternativ 1', '\n'.join(item.value for item in app.markdown))
