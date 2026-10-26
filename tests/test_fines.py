import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import fines_store as store


class FinesTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'PADEL_FINES_DB': str(Path(self.directory.name) / 'test.db')})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.directory.cleanup()

    def test_rate_snapshot_and_cancellation(self):
        fine_id, amount = store.give_fine('Benjamin', 'Dobbeltfejl', ['Benjamin'])
        self.assertEqual(amount, 10)
        store.update_rate('Dobbeltfejl', 25)
        self.assertEqual(store.give_fine('Benjamin', 'Dobbeltfejl', ['Benjamin'])[1], 25)
        store.set_cancelled(fine_id, True)
        fines = store.snapshot()['fines']
        self.assertEqual(sum(f['amount'] for f in fines if not f['cancelled']), 25)
        store.set_cancelled(fine_id, False)
        self.assertEqual(sum(f['amount'] for f in store.snapshot()['fines']), 35)

    def test_validation(self):
        with self.assertRaises(ValueError):
            store.give_fine('Ukendt', 'Dobbeltfejl', ['Benjamin'])
        with self.assertRaises(ValueError):
            store.update_rate('Dobbeltfejl', -5)

    def test_ui_give_and_undo(self):
        from streamlit.testing.v1 import AppTest
        app = AppTest.from_string("from fines_ui import render_fines\nrender_fines(['Benjamin', 'Rankedin Spiller'])").run()
        self.assertFalse(app.exception)
        next(b for b in app.button if b.label.startswith('Dobbeltfejl')).click().run()
        next(b for b in app.button if b.label.endswith('· Benjamin')).click().run()
        self.assertEqual(app.metric[0].value, '10 kr.')
        self.assertTrue(app.success)
        app.radio[0].set_value('Historik').run()
        next(b for b in app.button if b.label == 'Fortryd bøde').click().run()
        self.assertEqual(app.metric[0].value, '0 kr.')
        next(b for b in app.button if b.label == 'Gendan').click().run()
        self.assertEqual(app.metric[0].value, '10 kr.')
        self.assertFalse(app.exception)

    def test_empty_roster_preserves_history(self):
        from streamlit.testing.v1 import AppTest
        store.give_fine('Tidligere spiller', 'Dobbeltfejl', ['Tidligere spiller'])
        app = AppTest.from_string("from fines_ui import render_fines\nrender_fines([])").run()
        self.assertTrue(app.warning)
        self.assertFalse(any(b.label.startswith('+ ') for b in app.button))
        app.radio[0].set_value('Overblik').run()
        self.assertFalse(app.exception)
        self.assertEqual(app.dataframe[0].value.iloc[0]['Spiller'], 'Tidligere spiller')
        app.radio[0].set_value('Indstillinger').run()
        self.assertFalse(app.text_input)

    def test_fine_buttons_order_by_frequency_including_imported_quantities(self):
        from streamlit.testing.v1 import AppTest
        state = {'rules': [
            {'name': 'Billig', 'amount': 10}, {'name': 'Hyppig', 'amount': 100},
            {'name': 'Annulleret', 'amount': 20}, {'name': 'Aldrig', 'amount': 50}],
            'fines': [
                {'player': 'Benjamin', 'reason': 'Hyppig', 'quantity': 4, 'amount': 400, 'cancelled': False},
                {'player': 'Benjamin', 'reason': 'Billig', 'amount': 10, 'cancelled': False},
                {'player': 'Benjamin', 'reason': 'Billig', 'amount': 10, 'cancelled': False},
                {'player': 'Benjamin', 'reason': 'Annulleret', 'quantity': 100, 'amount': 2000, 'cancelled': True}]}
        with patch.object(store, 'snapshot', return_value=state):
            app = AppTest.from_string("from fines_ui import render_fines\nrender_fines(['Benjamin'])").run()
        self.assertFalse(app.exception)
        self.assertEqual([b.label.split(' · ')[0] for b in app.button if b.key.startswith('rule_')],
                         ['Hyppig', 'Billig', 'Aldrig', 'Annulleret'])

    def test_overview_breakdown_uses_quantities_and_historical_amounts(self):
        from streamlit.testing.v1 import AppTest
        state = {'rules': [], 'fines': [
            {'player': 'Benjamin', 'reason': 'Dobbeltfejl', 'quantity': 14, 'amount': 140, 'cancelled': False},
            {'player': 'Benjamin', 'reason': 'Dobbeltfejl', 'amount': 25, 'cancelled': False},
            {'player': 'Benjamin', 'reason': 'Glemt bat', 'amount': 100, 'cancelled': True},
            {'player': 'Jesper', 'reason': 'Glemt bat', 'amount': 100, 'cancelled': False},
        ]}
        with patch.object(store, 'snapshot', return_value=state):
            app = AppTest.from_string("from fines_ui import render_fines\nrender_fines(['Benjamin', 'Jesper', 'Kasper'])").run()
            app.radio[0].set_value('Overblik').run()
        self.assertFalse(app.exception)
        text = '\n'.join(item.value for item in app.markdown)
        self.assertIn('Benjamin · 165 kr.', text)
        self.assertIn('15 × Dobbeltfejl · 165 kr.', text)
        self.assertIn('Jesper · 100 kr.', text)
        self.assertIn('1 × Glemt bat · 100 kr.', text)
        self.assertIn('Kasper · 0 kr.', text)
        self.assertEqual(app.metric[0].value, '265 kr.')
