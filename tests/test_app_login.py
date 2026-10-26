import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from supabase_fines import FinesError, SupabaseFines
import fines_ui  # Load UI bindings before mocking the connection in route tests.


class AppLoginTests(unittest.TestCase):
    def test_every_entry_point_stops_before_fetching_team_data(self):
        for page in ('dashboard.py', 'pages/1_Holdforslag.py', 'pages/2_Boedekasse.py', 'pages/3_Kampplanlaegning.py'):
            with self.subTest(page=page), patch('fines_connection.get_store', return_value=None), \
                    patch('padel_pipeline.build_dataset') as fetch:
                app = AppTest.from_file(page).run()
                self.assertFalse(app.exception)
                fetch.assert_not_called()
                self.assertFalse(app.tabs)
                self.assertFalse(app.dataframe)

    def test_unapproved_account_cannot_continue(self):
        backend = SupabaseFines('https://project.supabase.co', 'sb_publishable_test', {})
        with patch('fines_connection.get_store', return_value=backend), \
                patch.object(backend, 'snapshot', side_effect=FinesError('Ingen holdadgang')):
            app = AppTest.from_string("from fines_connection import require_app_login\nimport streamlit as st\nrequire_app_login()\nst.write('PRIVATE TEAM DATA')").run()
        self.assertFalse(app.exception)
        self.assertTrue(app.error)
        self.assertNotIn('PRIVATE TEAM DATA', [m.value for m in app.markdown])

    def test_approved_account_can_continue(self):
        backend = SupabaseFines('https://project.supabase.co', 'sb_publishable_test', {})
        with patch('fines_connection.get_store', return_value=backend), \
                patch.object(backend, 'snapshot', return_value={'role': 'member'}):
            app = AppTest.from_string("from fines_connection import require_app_login\nimport streamlit as st\nrequire_app_login()\nst.write('PRIVATE TEAM DATA')").run()
        self.assertFalse(app.exception)
        self.assertIn('PRIVATE TEAM DATA', [m.value for m in app.markdown])
