import copy
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from streamlit.testing.v1 import AppTest
from planning_store import PlanningStore, make_slots, slot_summary
from supabase_fines import SharedSupabaseFines, FinesError


def sample_state():
    poll_id = str(uuid4())
    return dict(players=[dict(player_id=1, name='Anna'), dict(player_id=2, name='Bo')],
                polls=[dict(id=poll_id, season_key='test', title='Sæsonstart', status='open',
                            deadline=None, final_slot=None, version=1,
                            slots=make_slots(poll_id, ['2027-01-02T10:00', '2027-01-03T14:00']))], votes=[])


class FakeStore:
    def __init__(self):
        self.state = sample_state()

    def snapshot(self, season):
        return copy.deepcopy(self.state)

    def save_vote(self, poll, player_id, selected, version=0):
        self.state['votes'] = [v for v in self.state['votes'] if v['player_id'] != player_id]
        self.state['votes'].append(dict(poll_id=poll['id'], player_id=player_id, version=version + 1,
                                       answers={s['id']: s['id'] in selected for s in poll['slots']}))

    def save_poll(self, poll):
        poll = dict(poll, version=poll.get('version', 0) + 1)
        self.state['polls'] = [p for p in self.state['polls'] if p['id'] != poll['id']] + [poll]


class PlanningTests(unittest.TestCase):
    def test_stable_slot_ids_and_unanswered_new_times(self):
        state = sample_state()
        poll = state['polls'][0]
        slots = make_slots(poll['id'], ['2027-01-02T10:00', '2027-01-02T10:00', '2027-01-04T14:00'])
        self.assertEqual(len(slots), 2)
        self.assertEqual(slots[0]['id'], poll['slots'][0]['id'])
        state['votes'] = [dict(poll_id=poll['id'], player_id=1, answers={poll['slots'][0]['id']: True, poll['slots'][1]['id']: False})]
        poll['slots'] = slots
        rows = slot_summary(poll, state['votes'], state['players'])
        self.assertEqual(rows[0]['yes'], ['Anna'])
        self.assertEqual(rows[0]['pending'], ['Bo'])
        self.assertEqual(rows[1]['pending'], ['Anna', 'Bo'])

    def test_each_request_rechecks_shared_login(self):
        authorized = Mock(return_value=True)
        backend = SharedSupabaseFines('https://test.supabase.co', 'sb_publishable_test', 'sb_secret_test', authorized)
        store = PlanningStore(backend)
        with patch('supabase_fines.requests.request') as request:
            authorized.return_value = False
            with self.assertRaises(FinesError):
                store.snapshot('test')
            with self.assertRaises(FinesError):
                store.save_poll(sample_state()['polls'][0])
            with self.assertRaises(FinesError):
                store.save_vote(sample_state()['polls'][0], 1, [])
            request.assert_not_called()

    def app(self):
        return AppTest.from_string("from planning_ui import render_planning\nrender_planning(None, 'test', 'Testsæson')")

    def test_player_selects_multiple_times_and_can_change_to_none(self):
        store = FakeStore()
        with patch('planning_ui.PlanningStore', return_value=store):
            app = self.app().run()
            app.selectbox(key='planning_player').set_value(1).run()
            choices = [c for c in app.checkbox if 'kl.' in c.label]
            for checkbox in choices:
                checkbox.check()
            next(b for b in app.button if b.label == 'Gem mine svar').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(list(store.state['votes'][0]['answers'].values()), [True, True])
            self.assertTrue(app.success)
            for checkbox in app.checkbox:
                if 'kl.' in checkbox.label:
                    checkbox.uncheck()
                elif checkbox.label == 'Jeg kan ingen af tidspunkterne':
                    checkbox.check()
            next(b for b in app.button if b.label == 'Gem mine svar').click().run()
            self.assertFalse(app.exception)
            self.assertFalse(any(store.state['votes'][0]['answers'].values()))
            rows = slot_summary(store.state['polls'][0], store.state['votes'], store.state['players'])
            self.assertEqual(rows[0]['no'], ['Anna'])
            self.assertEqual(rows[0]['pending'], ['Bo'])

    def test_create_without_captain_code_and_repeat_dates(self):
        store = FakeStore()
        with patch('planning_ui.PlanningStore', return_value=store):
            app = self.app().run()
            next(b for b in app.button if b.label == 'Opret dato').click().run()
            self.assertFalse(any('kode' in w.label.lower() for w in app.text_input))
            next(w for w in app.number_input if w.label == 'Gentag i efterfølgende uger').set_value(2)
            next(b for b in app.button if b.label == 'Tilføj tidspunkter' and 'planning_edit_' in b.key).click().run()
            next(w for w in app.text_input if w.label == 'Navn på forslag / modstander').set_value('Ny kamp')
            next(b for b in app.button if b.label == 'Udgiv datoer').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(len(store.state['polls']), 2)
            self.assertEqual(len(store.state['polls'][-1]['slots']), 3)

    def test_finalized_poll_disables_answers(self):
        store = FakeStore()
        store.state['polls'][0].update(status='final', final_slot=store.state['polls'][0]['slots'][0]['id'])
        with patch('planning_ui.PlanningStore', return_value=store):
            app = self.app().run()
            app.selectbox(key='planning_player').set_value(1).run()
            self.assertFalse(app.exception)
            self.assertTrue(next(b for b in app.button if b.label == 'Gem mine svar').disabled)


if __name__ == '__main__':
    unittest.main()
