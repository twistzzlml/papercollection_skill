"""Conservative Zotero Local/Web API synchronization; no database access."""
import argparse
import hashlib
import html
import json
import os
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from roadmap import check_run, load_run, write_json, write_jsonl


def new_key():
    return ''.join(secrets.choice('23456789ABCDEFGHIJKLMNPQRSTUVWXYZ') for _ in range(8))


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def norm_doi(value):
    return re.sub(r'^(https?://(dx\.)?doi\.org/|doi:\s*)', '', value.strip(), flags=re.I).lower()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RuntimeError('Unexpected API redirect; refusing to forward credentials')


class API:
    def __init__(self, mode='local', library='users/0', authorize=False):
        if not re.fullmatch(r'(users|groups)/\d+', library):
            raise ValueError('library must be users/<id> or groups/<id>')
        if mode == 'web' and library == 'users/0':
            raise ValueError('Web API needs real user ID')
        self.library, self.mode, self.authorize = library, mode, authorize
        self.base = 'http://127.0.0.1:23119/api/' if mode == 'local' else 'https://api.zotero.org/'
        self.key = os.environ.get('ZOTERO_LOCAL_API_KEY' if mode == 'local' else 'ZOTERO_API_KEY')
        self.headers = {'Zotero-API-Version': '3', 'User-Agent': 'literature-roadmap/1'}
        self.opener = urllib.request.build_opener(NoRedirect())
        if mode == 'local':
            _, headers = self.request('GET', '')
            self.server_id = headers.get('Zotero-Server-ID')
            if self.server_id:
                self.headers['Zotero-Server-ID'] = self.server_id
            self.partition = 'local/' + str(self.server_id) + '/' + library
        else:
            self.partition = 'web/' + library

    def request(self, method, path, data=None, headers=None):
        merged = dict(self.headers)
        if self.key:
            merged['Zotero-API-Key'] = self.key
        if headers:
            merged.update(headers)
        payload = None if data is None else json.dumps(data).encode('utf-8')
        if payload:
            merged['Content-Type'] = 'application/json'
        req = urllib.request.Request(self.base + path, data=payload, headers=merged, method=method)
        with self.opener.open(req, timeout=60) as response:
            raw = response.read()
            # API root may return a human-readable greeting.
            try:
                result = json.loads(raw) if raw else None
            except ValueError:
                result = None
            return result, response.headers

    def write(self, method, path, data, headers=None):
        if self.mode == 'local' and not getattr(self, 'server_id', None):
            raise RuntimeError('Local write capability not detected (Zotero 10+ required)')
        if not self.key and self.mode == 'local' and self.authorize:
            result, _ = self.request('POST', 'local/authorize', {'appName': 'Literature Roadmap'})
            self.key = result['key']  # Memory only; never persist or print.
        if not self.key:
            raise RuntimeError('No write credential; authorize local API or configure environment')
        try:
            result, _ = self.request(method, path, data, headers)
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                self.key = None
            raise
        if isinstance(result, dict) and result.get('failed'):
            raise RuntimeError('Zotero rejected one or more objects; inspect schema and permissions')
        return result

    def get(self, kind, key):
        try:
            return self.request('GET', self.library + '/' + kind + '/' + key)[0]
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise

    def find(self, title):
        results, start = [], 0
        while True:
            query = urllib.parse.urlencode(dict(q=title, qmode='everything', limit=100, start=start))
            batch, _ = self.request('GET', self.library + '/items/top?' + query)
            results.extend(batch)
            if len(batch) < 100:
                return results
            start += len(batch)

    def put_new(self, kind, data):
        # Explicit keys are conditional writes: version 0 asserts the object is new.
        data = {**data, 'version': 0}
        if kind == 'items':
            data = {'tags': [], 'collections': [], 'relations': {}, **data}
        self.write('POST', self.library + '/' + kind, [data],
                   {'Zotero-Write-Token': digest(self.partition + kind + data['key'])[:32]})

    def patch(self, kind, key, fields, version):
        self.write('PATCH', self.library + '/' + kind + '/' + key, fields,
                   {'If-Unmodified-Since-Version': str(version)})


def sync_paper(api, p, collections, run_id, save):
    if p.get('decision') != 'include':
        return
    z = p.setdefault('zotero', {})
    if z.get('partition') and z['partition'] != api.partition:
        raise ValueError('Zotero library/server changed; re-resolve identities before writing')
    z['partition'], z['status'] = api.partition, 'pending'
    item = api.get('items', z['key']) if z.get('key') else None
    if not z.get('key'):
        candidates = api.find(norm_doi(p['doi'])) if p.get('doi') else []
        candidates = list({x['key']: x for x in candidates + api.find(p['title'])}.values())
        exact_doi = [x for x in candidates if p.get('doi') and
                     norm_doi(x['data'].get('DOI', '')) == norm_doi(p['doi'])]
        if len(exact_doi) == 1:
            item = exact_doi[0]
        elif candidates:
            # Title alone can conflate versions or different works; agent must select a key.
            raise ValueError('Possible existing versions: verify and set zotero.key before sync')
        if item:
            z['key'] = item['key']
        else:
            if not p.get('metadata_verified'):
                raise ValueError('Verify metadata before creating Zotero item')
            z['key'], z['created_by_run'] = new_key(), True
        save()  # Key survives unknown write outcomes.
    if item is None:
        if not z.get('created_by_run'):
            raise ValueError('Mapped Zotero item missing; do not silently recreate')
        data = dict(p.get('zotero_data', {}))
        data.update(key=z['key'], itemType=data.get('itemType', 'journalArticle'),
                    title=p['title'], collections=sorted(set(collections)))
        if p.get('doi'):
            data['DOI'] = norm_doi(p['doi'])
        if p.get('url'):
            data['url'] = p['url']
        if p.get('year'):
            data.setdefault('date', str(p['year']))
        if p.get('authors'):
            data.setdefault('creators', [{'creatorType': 'author', 'name': a} for a in p['authors']])
        z['pending_added_collections'] = sorted(set(collections))
        save()
        api.put_new('items', data)
        item = api.get('items', z['key'])
        if not item:
            raise RuntimeError('Created item failed readback')
    current = item['data']
    if current.get('itemType') in ('note', 'attachment'):
        raise ValueError('Mapped key is not a bibliographic parent')
    current_cols, desired = set(current.get('collections', [])), set(collections)
    managed = set(z.get('added_collections', [])) | set(z.get('pending_added_collections', []))
    added = (managed & desired) | (desired - current_cols)
    merged = sorted((current_cols - managed) | desired)
    z['pending_added_collections'] = sorted(managed | added)
    save()
    if sorted(current.get('collections', [])) != merged:
        api.patch('items', z['key'], {'collections': merged}, item['version'])
    item = api.get('items', z['key'])
    if not item or sorted(item['data'].get('collections', [])) != merged:
        raise RuntimeError('Collection membership failed readback')
    z['added_collections'] = sorted(added)
    z.pop('pending_added_collections', None)
    save()
    marker = 'literature-roadmap:' + run_id + ':' + p['id']
    note = '<p>' + html.escape(marker) + '</p><p>' + html.escape(p.get('summary', '待阅读')) + '</p>'
    note += '<p>阅读：' + html.escape(p.get('reading', 'pending')) + '</p>'
    if p.get('evidence'):
        note += '<p>依据：' + html.escape(p['evidence']) + '</p>'
    if not z.get('note_key'):
        z['note_key'] = new_key()
        save()
    existing = api.get('items', z['note_key'])
    if existing:
        actual = existing['data'].get('note', '')
        if existing['data'].get('parentItem') != z['key'] or marker not in actual:
            raise ValueError('Note ownership mismatch')
        if actual != note:
            if digest(actual) not in (z.get('note_hash'), z.get('pending_note_hash')):
                raise ValueError('Owned note edited externally; preserve it and resolve conflict')
            z['pending_note_hash'] = digest(note)
            save()
            api.patch('items', z['note_key'], {'note': note}, existing['version'])
    else:
        z['pending_note_hash'] = digest(note)
        save()
        api.put_new('items', dict(key=z['note_key'], itemType='note', parentItem=z['key'], note=note))
    saved_note = api.get('items', z['note_key'])
    if not saved_note or saved_note['data'].get('note') != note:
        raise RuntimeError('Note failed readback (possibly HTML normalization); inspect before retry')
    z['note_hash'] = digest(note)
    z.pop('pending_note_hash', None)
    prefix = 'library' if api.library.startswith('users/') else api.library
    z.update(status='synced', select_uri='zotero://select/' + prefix + '/items/' + z['key'])
    save()


def sync_run(api, path):
    path = Path(path)
    errors, _ = check_run(path)
    if errors:
        raise ValueError('\n'.join(errors))
    state, papers, _ = load_run(path)
    if not state.get('gates', {}).get('scope'):
        raise ValueError('Scope must be confirmed before sync')
    z = state.setdefault('zotero', {})
    if z.get('partition') and z['partition'] != api.partition:
        raise ValueError('Library/server mismatch; explicit identity reconciliation required')
    z['partition'] = api.partition
    mapping = z.setdefault('collections', {})

    def save_state():
        write_json(path / 'state.json', state)

    def collection(tid, name, parent):
        if tid not in mapping:
            mapping[tid] = new_key()
            save_state()
        key = mapping[tid]
        obj = api.get('collections', key)
        desired = dict(name=name, parentCollection=parent or False)
        if obj is None:
            api.put_new('collections', dict(key=key, **desired))
        elif any(obj['data'].get(k) != v for k, v in desired.items()):
            # Existing managed collection may have been edited by the user; preserve it.
            raise ValueError('Managed collection changed; reconcile before updating: ' + tid)
        obj = api.get('collections', key)
        if not obj or any(obj['data'].get(k) != v for k, v in desired.items()):
            raise RuntimeError('Collection failed readback')
        return key

    root = collection('__root__', state['title'] + ' [' + state['run_id'][:8] + ']', None)
    done = {}

    def add_topic(t):
        if t['id'] not in done:
            parent = root if not t.get('parent') else add_topic(next(x for x in state['topics'] if x['id'] == t['parent']))
            done[t['id']] = collection(t['id'], t['title'], parent)
        return done[t['id']]

    for t in state['topics']:
        add_topic(t)
    failures = []
    for paper in papers:
        if paper.get('decision') != 'include':
            continue
        try:
            sync_paper(api, paper, [root] + [done[t] for t in paper['topics']], state['run_id'],
                       lambda: write_jsonl(path / 'papers.jsonl', papers))
        except (ValueError, RuntimeError, OSError) as exc:
            paper.setdefault('zotero', {})['status'] = 'pending'
            paper['zotero']['error_type'] = type(exc).__name__
            failures.append(paper['id'] + ': ' + str(exc))
            write_jsonl(path / 'papers.jsonl', papers)
            if isinstance(exc, urllib.error.HTTPError) and exc.code in (401, 403, 429):
                break  # No authorization-dialog spam or blind rate-limit retries.
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['probe', 'sync'])
    parser.add_argument('run', type=Path, nargs='?')
    parser.add_argument('--mode', choices=['local', 'web'], default='local')
    parser.add_argument('--library', default='users/0')
    parser.add_argument('--authorize-local', action='store_true')
    args = parser.parse_args()
    try:
        api = API(args.mode, args.library, args.authorize_local)
        if args.command == 'probe':
            api.request('GET', api.library + '/items?limit=1')
            print(json.dumps(dict(readable=True, partition=api.partition,
                  local_write_capability=bool(getattr(api, 'server_id', None)),
                  write_verified=False)))
        elif not args.run:
            parser.error('sync requires run directory')
        else:
            failures = sync_run(api, args.run)
            print(json.dumps(dict(failures=failures), ensure_ascii=False))
            return bool(failures)
    except (OSError, ValueError, RuntimeError) as exc:
        print(type(exc).__name__ + ': ' + str(exc))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
