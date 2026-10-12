import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from zotero_sync import API, sync_paper


class FakeAPI:
    partition = 'test/users/0'
    library = 'users/0'

    def __init__(self):
        self.items = {}
        self.writes = 0
        self.fail_note = False

    def get(self, kind, key):
        return copy.deepcopy(self.items.get(key))

    def find(self, title):
        return [copy.deepcopy(v) for v in self.items.values()
                if v['data'].get('title') == title or v['data'].get('DOI') == title]

    def put_new(self, kind, data):
        if self.fail_note and data['itemType'] == 'note':
            raise RuntimeError('note write failed')
        if data['key'] in self.items:
            raise RuntimeError('duplicate key')
        self.writes += 1
        self.items[data['key']] = {'key': data['key'], 'version': 1, 'data': copy.deepcopy(data)}

    def patch(self, kind, key, fields, version):
        if self.items[key]['version'] != version:
            raise RuntimeError('version conflict')
        self.writes += 1
        self.items[key]['data'].update(copy.deepcopy(fields))
        self.items[key]['version'] += 1


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeAPI()
        self.p = dict(id='p1', title='Real title', doi='10.1/test', summary='A < B',
                      decision='include', year=2025, authors=['A Researcher'],
                      zotero={}, metadata_verified=True)
        self.checkpoints = []

    def save(self):
        self.checkpoints.append(copy.deepcopy(self.p))

    def test_repeated_sync_does_not_duplicate(self):
        sync_paper(self.api, self.p, ['COL1', 'COL2'], 'run1', self.save)
        count = self.api.writes
        sync_paper(self.api, self.p, ['COL1', 'COL2'], 'run1', self.save)
        self.assertEqual(len(self.api.items), 2)
        self.assertEqual(count, self.api.writes)
        self.assertEqual(self.p['zotero']['status'], 'synced')

    def test_existing_item_preserves_fields_and_memberships(self):
        original = dict(key='EXISTING', itemType='journalArticle', title='Real title',
                        DOI='10.1/test', collections=['USERCOL'], tags=[{'tag': 'user'}],
                        abstractNote='User abstract')
        self.api.items['EXISTING'] = dict(key='EXISTING', version=7, data=original)
        sync_paper(self.api, self.p, ['COL1'], 'run1', self.save)
        data = self.api.items['EXISTING']['data']
        self.assertEqual(data['collections'], ['COL1', 'USERCOL'])
        self.assertEqual(data['abstractNote'], 'User abstract')
        self.assertEqual(data['tags'], [{'tag': 'user'}])
        self.assertEqual(len(self.api.items), 2)

    def test_partial_failure_resumes_known_key(self):
        self.api.fail_note = True
        with self.assertRaises(RuntimeError):
            sync_paper(self.api, self.p, ['COL1'], 'run1', self.save)
        self.assertNotEqual(self.p['zotero'].get('status'), 'synced')
        self.assertTrue(self.checkpoints[-1]['zotero']['key'])
        self.api.fail_note = False
        sync_paper(self.api, self.p, ['COL1'], 'run1', self.save)
        self.assertEqual(len(self.api.items), 2)

    def test_ambiguous_title_is_not_automatically_merged(self):
        self.p.pop('doi')
        for k in ['AAA', 'BBB']:
            self.api.items[k] = dict(key=k, version=1, data=dict(title='Real title', itemType='journalArticle'))
        with self.assertRaises(ValueError):
            sync_paper(self.api, self.p, ['COL1'], 'run1', self.save)
        self.assertEqual(self.api.writes, 0)

    def test_no_verified_metadata_no_new_item(self):
        self.p['metadata_verified'] = False
        with self.assertRaises(ValueError):
            sync_paper(self.api, self.p, ['COL1'], 'run1', self.save)
        self.assertEqual(self.api.writes, 0)

    def test_user_edited_owned_note_is_not_overwritten(self):
        sync_paper(self.api, self.p, ['COL1'], 'run1', self.save)
        key = self.p['zotero']['note_key']
        self.api.items[key]['data']['note'] += '<p>User addition</p>'
        self.p['summary'] = 'Changed'
        with self.assertRaises(ValueError):
            sync_paper(self.api, self.p, ['COL1'], 'run1', self.save)
        self.assertIn('User addition', self.api.items[key]['data']['note'])

    def test_same_doi_with_changed_title_reuses_item(self):
        self.api.items['OLDKEY'] = dict(key='OLDKEY', version=1,
             data=dict(title='An earlier title', DOI='10.1/test', itemType='journalArticle'))
        sync_paper(self.api, self.p, ['COL1'], 'run1', self.save)
        self.assertEqual(self.p['zotero']['key'], 'OLDKEY')
        self.assertEqual(len(self.api.items), 2)

    def test_api_new_items_supply_required_containers(self):
        api = API.__new__(API)
        api.partition, api.library = 'test', 'users/0'
        calls = []
        api.write = lambda *args: calls.append(args)
        api.put_new('items', dict(key='ABCDEF12', itemType='note', parentItem='PARENT12', note='x'))
        payload = calls[0][2][0]
        for field in ('tags', 'collections', 'relations'):
            self.assertIn(field, payload)
        self.assertEqual(payload.get('version'), 0)
        api.put_new('collections', dict(key='COLLECT2', name='Test', parentCollection=False))
        self.assertEqual(calls[-1][2][0].get('version'), 0)

    def test_reclassification_removes_only_run_added_memberships(self):
        self.api.items['EXISTING'] = dict(key='EXISTING', version=1,
            data=dict(title='Real title', DOI='10.1/test', itemType='journalArticle', collections=['USERCOL', 'PREEXIST']))
        sync_paper(self.api, self.p, ['COLA', 'PREEXIST'], 'run1', self.save)
        sync_paper(self.api, self.p, ['COLB'], 'run1', self.save)
        self.assertEqual(self.api.items['EXISTING']['data']['collections'], ['COLB', 'PREEXIST', 'USERCOL'])


if __name__ == '__main__':
    unittest.main()
