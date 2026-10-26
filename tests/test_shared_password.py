import os
import unittest
from unittest.mock import patch, Mock

from streamlit.testing.v1 import AppTest
from supabase_fines import SharedSupabaseFines, FinesError


class SharedPasswordTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'APP_PASSWORD': 'test-fælleskode-123', 'SUPABASE_SECRET_KEY': 'sb_secret_test'})
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def app(self):
        return AppTest.from_string("from fines_connection import require_app_login\nimport streamlit as st\nrequire_app_login()\nst.write('PRIVATE TEAM DATA')")

    def test_wrong_password_never_fetches_data(self):
        with patch('supabase_fines.requests.request') as request:
            app = self.app().run()
            app.text_input[0].set_value('wrong')
            app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertTrue(app.error)
        request.assert_not_called()
        self.assertNotIn('PRIVATE TEAM DATA', [m.value for m in app.markdown])

    def test_password_unlocks_shared_session_then_rotation_locks_it(self):
        with patch.object(SharedSupabaseFines, 'snapshot', return_value={'role': 'admin'}):
            app = self.app().run()
            self.assertEqual([i.label for i in app.text_input], ['Fælles adgangskode'])
            app.text_input[0].set_value('test-fælleskode-123')
            app.button[0].click().run()
            self.assertIn('PRIVATE TEAM DATA', [m.value for m in app.markdown])
            version = app.session_state['shared_password_version']
            locked = self.app()
            locked.session_state['shared_password_version'] = version
            with patch.dict(os.environ, {'APP_PASSWORD': 'changed-code'}):
                locked.run()
            self.assertNotIn('PRIVATE TEAM DATA', [m.value for m in locked.markdown])
            self.assertTrue(locked.text_input)

    def test_partial_configuration_does_not_fall_back_to_personal_login(self):
        with patch.dict(os.environ, {'SUPABASE_SECRET_KEY': ''}):
            app = self.app().run()
        self.assertTrue(app.error)
        self.assertFalse(app.radio)

    def test_direct_routes_are_protected_before_rankedin_fetch(self):
        for page in ('dashboard.py', 'pages/1_Holdforslag.py', 'pages/2_Boedekasse.py', 'pages/3_Kampplanlaegning.py'):
            with self.subTest(page=page), patch('padel_pipeline.build_dataset') as fetch:
                app = AppTest.from_file(page).run()
                self.assertFalse(app.exception)
                self.assertEqual([i.label for i in app.text_input], ['Fælles adgangskode'])
                fetch.assert_not_called()

    @patch('supabase_fines.requests.request')
    def test_server_client_checks_authorization_on_every_call(self, request):
        authorized = Mock(return_value=False)
        backend = SharedSupabaseFines('https://project.supabase.co', 'sb_publishable_test', 'sb_secret_test', authorized)
        with self.assertRaises(FinesError):
            backend.snapshot()
        request.assert_not_called()
        authorized.return_value = True
        request.return_value = Mock(ok=True, status_code=200, content=b'json', json=lambda: {'fines': [], 'rules': []})
        self.assertEqual(backend.snapshot()['role'], 'admin')
        self.assertEqual(request.call_args.kwargs['headers']['apikey'], 'sb_secret_test')
        self.assertNotIn('Authorization', request.call_args.kwargs['headers'])
        authorized.return_value = False
        with self.assertRaises(FinesError):
            backend.set_cancelled('id', True)
        self.assertEqual(request.call_count, 1)
