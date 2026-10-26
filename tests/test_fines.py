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
        fine_id, amount = store.give_fine('Benjamin', 'Dobbeltfejl')
        self.assertEqual(amount, 10)
        store.update_rate('Dobbeltfejl', 25)
        self.assertEqual(store.give_fine('Benjamin', 'Dobbeltfejl')[1], 25)
        store.set_cancelled(fine_id, True)
        fines = store.snapshot()['fines']
        self.assertEqual(sum(f['amount'] for f in fines if not f['cancelled']), 25)
        store.set_cancelled(fine_id, False)
        self.assertEqual(sum(f['amount'] for f in store.snapshot()['fines']), 35)

    def test_validation(self):
        with self.assertRaises(ValueError):
            store.add_player('benjamin')
        with self.assertRaises(ValueError):
            store.give_fine('Ukendt', 'Dobbeltfejl')
        with self.assertRaises(ValueError):
            store.update_rate('Dobbeltfejl', -5)

    def test_ui_give_and_undo(self):
        from streamlit.testing.v1 import AppTest
        app = AppTest.from_file('pages/2_Boedekasse.py').run()
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
