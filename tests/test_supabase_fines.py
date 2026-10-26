import unittest
from unittest.mock import Mock, patch
from supabase_fines import SupabaseFines, FinesError
from prepare_fines_import import prepare, import_sql


def response(status, data):
    return Mock(status_code=status, ok=status < 400, content=b'json', json=lambda: data)


class RemoteFinesTests(unittest.TestCase):
    def backend(self):
        return SupabaseFines('https://project.supabase.co', 'sb_publishable_test', {'access_token': 'user-token'})

    @patch('supabase_fines.requests.request')
    def test_uses_user_token_and_stable_player_id(self, request):
        request.return_value = response(201, [{'id': 'same-id', 'amount': 10}])
        result = self.backend().give_fine('New Name', 'Dobbeltfejl', [{'player_id': 42, 'name': 'New Name'}], 'same-id')
        self.assertEqual(result, ('same-id', 10))
        sent = request.call_args.kwargs
        self.assertEqual(sent['json'], {'id': 'same-id', 'player_id': 42, 'reason': 'Dobbeltfejl'})
        self.assertEqual(sent['headers']['Authorization'], 'Bearer user-token')
        self.assertNotIn('amount', sent['json'])

    @patch('supabase_fines.requests.request')
    def test_retry_reads_existing_id_without_duplicate(self, request):
        request.side_effect = [response(409, {}), response(200, [{'id': 'same-id', 'amount': 10}])]
        result = self.backend().give_fine('Name', 'Dobbeltfejl', [{'player_id': 42, 'name': 'Name'}], 'same-id')
        self.assertEqual(result, ('same-id', 10))
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args.kwargs['params']['id'], 'eq.same-id')

    @patch('supabase_fines.requests.request')
    def test_unknown_player_never_writes(self, request):
        with self.assertRaises(FinesError):
            self.backend().give_fine('Other', 'Dobbeltfejl', [{'player_id': 42, 'name': 'Name'}])
        request.assert_not_called()

    @patch('supabase_fines.requests.request')
    def test_revoked_membership_denied(self, request):
        request.return_value = response(200, {'role': None, 'fines': [], 'rules': []})
        backend = self.backend()
        backend.session['expires_at'] = 9999999999
        with self.assertRaises(FinesError):
            backend.snapshot()

    @patch('supabase_fines.requests.request')
    def test_refresh_failure_clears_only_own_session(self, request):
        first = self.backend()
        second = self.backend()
        first.session.update(expires_at=0, refresh_token='old')
        request.return_value = response(401, {})
        with self.assertRaises(FinesError):
            first.refresh()
        self.assertEqual(first.session, {})
        self.assertEqual(second.session['access_token'], 'user-token')

    def test_secret_key_rejected(self):
        with self.assertRaises(FinesError):
            SupabaseFines('https://project.supabase.co', 'sb_secret_forbidden', {})


class ImportTests(unittest.TestCase):
    def test_preserves_quantity_unknown_date_and_stable_source_identity(self):
        text = ',PADEL · HISTORIK,\n0,ID,Tidspunkt,Spiller,Bøde,Antal,Sats,Beløb,Annulleret,Kilde / note\n1,START-1,,Benjamin,Dobbeltfejl,14,10,140,False,Starttal\n'
        roster = [{'name': 'Benjamin Andersen', 'player_id': 42}]
        rows = prepare(text, roster)
        self.assertEqual(rows[0]['quantity'], 14)
        self.assertIsNone(rows[0]['created'])
        self.assertEqual(rows[0]['id'], prepare(text, roster)[0]['id'])
        self.assertIn('on conflict(source_id) do nothing', import_sql(rows, roster))

    def test_unknown_player_aborts_import(self):
        text = ',PADEL · HISTORIK,\n0,ID,Tidspunkt,Spiller,Bøde,Antal,Sats,Beløb,Annulleret,Kilde / note\n1,X,,Unknown,Dobbeltfejl,1,10,10,False,Note\n'
        with self.assertRaises(ValueError):
            prepare(text, [])
