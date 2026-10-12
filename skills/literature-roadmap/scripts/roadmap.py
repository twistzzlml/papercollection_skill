"""Persistent survey checks and native XMind 8 export. Python stdlib only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import uuid
import zipfile
from datetime import date
from xml.etree import ElementTree as ET

NS = 'urn:xmind:xmap:xmlns:content:2.0'
XLINK = 'http://www.w3.org/1999/xlink'
ET.register_namespace('', NS)
ET.register_namespace('xlink', XLINK)


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def write_json(path, value):
    atomic_write(path, (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))


def write_jsonl(path, values):
    atomic_write(path, ''.join(json.dumps(v, ensure_ascii=False) + '\n' for v in values).encode('utf-8'))


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8-sig').splitlines() if line.strip()]


def init_run(path, title):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=False)
    write_json(path / 'state.json', dict(schema_version=1, run_id=uuid.uuid4().hex,
               title=title, created=str(date.today()), scope_version=1, phase='scope',
               gates={}, coverage='in_progress', topics=[], relations=[],
               limitations=[], zotero={}, exports={}))
    for name in ('papers.jsonl', 'queue.jsonl'):
        atomic_write(path / name, b'')
    atomic_write(path / 'scope.md', ('# ' + title + '\n\n'
                 '范围版本：1\n状态：待确认\n\n'
                 '## 已确认执行约定\n\n研究目的：\n纳入边界：\n排除边界：\n'
                 '方法关注点：\n语言：仅英文。\n发表门槛：排除已核实非 CCF 期刊，预印本豁免；非 CCF 会议按范围约定。\n'
                 '时间优先级：CCF A/B/C 与执行日前两年预印本。\n检索词与组合：\n'
                 '主检索：Google Scholar\n输出：Zotero、XMind，证据留在 Markdown。\n'
                 '确认记录：\n\n## 讨论与变更\n').encode('utf-8'))
    atomic_write(path / 'evidence.md', b'# Evidence and decisions\n')


def load_run(path):
    path = Path(path)
    return (json.loads((path / 'state.json').read_text(encoding='utf-8-sig')),
            read_jsonl(path / 'papers.jsonl'), read_jsonl(path / 'queue.jsonl'))


def check_run(path):
    state, papers, queue = load_run(path)
    errors, warnings = [], []
    if not isinstance(state, dict):
        return ['state must be an object'], []
    for key, typ in [('topics', list), ('relations', list), ('gates', dict), ('zotero', dict),
                     ('limitations', list), ('title', str), ('run_id', str), ('scope_version', int)]:
        if not isinstance(state.get(key), typ):
            errors.append('invalid/missing state ' + key)
    if state.get('phase') not in ('scope', 'seeds', 'taxonomy', 'expansion', 'review'):
        errors.append('invalid/missing phase')
    if state.get('coverage') not in ('in_progress', 'blocked', 'complete'):
        errors.append('invalid coverage')
    topics = state.get('topics', [])
    if not isinstance(topics, list) or not isinstance(state.get('relations'), list):
        return errors, warnings
    for kind, entries in [('topic', topics), ('paper', papers), ('queue', queue), ('relation', state['relations'])]:
        if any(not isinstance(x, dict) for x in entries):
            errors.append(kind + ' entries must be objects')
            return errors, warnings
    for t in topics:
        if not isinstance(t.get('title'), str) or not t.get('title'):
            errors.append('topic title required')
        if t.get('parent') is not None and not isinstance(t['parent'], str):
            errors.append('topic parent must be string/null')
    for p in papers:
        if not isinstance(p.get('topics', []), list) or any(not isinstance(x, str) for x in p.get('topics', [])):
            errors.append('paper topics must be a list of IDs')
        if not isinstance(p.get('zotero', {}), dict):
            errors.append('paper zotero must be object')
    for q in queue:
        if q.get('kind') not in ('query', 'backward', 'forward', 'fulltext', 'verify'):
            errors.append('queue kind required')
        if q.get('status') not in ('pending', 'running', 'blocked', 'done', 'excluded'):
            errors.append('queue status required')
        for key in ('scope_version', 'source', 'next', 'reason'):
            if key not in q:
                errors.append('queue ' + key + ' required')
    if errors:
        return errors, warnings
    if state.get('schema_version') != 1:
        errors.append('unsupported schema_version')
    if not state.get('run_id') or not (Path(path) / 'scope.md').is_file():
        errors.append('missing run_id or scope.md')
    topics = state.get('topics', [])
    ids = [t.get('id') for t in topics]
    pids = [p.get('id') for p in papers]
    for kind, values in [('topic', ids), ('paper', pids), ('queue', [q.get('id') for q in queue])]:
        if any(not isinstance(x, str) or not x for x in values) or len(set(values)) != len(values):
            errors.append('missing/duplicate ' + kind + ' id')
    if any(not isinstance(x, str) or not x for x in ids + pids + [q.get('id') for q in queue]):
        return errors, warnings
    parents = {t['id']: t.get('parent') for t in topics if t.get('id')}
    for tid, parent in parents.items():
        seen = {tid}
        while parent is not None:
            if parent not in parents:
                errors.append('unknown parent ' + str(parent)); break
            if parent in seen:
                errors.append('topic cycle ' + tid); break
            seen.add(parent)
            parent = parents[parent]
    included = {p['id'] for p in papers if p.get('decision') == 'include'}
    for p in papers:
        pid = p.get('id', '?')
        if p.get('decision') not in ('include', 'exclude', 'pending'):
            errors.append(pid + ': invalid decision')
        if not p.get('title'):
            errors.append(pid + ': missing title')
        if p.get('decision') in ('include', 'exclude') and not p.get('reason'):
            errors.append(pid + ': missing decision reason')
        if pid in included and not p.get('topics'):
            errors.append(pid + ': included paper has no topic')
        for tid in p.get('topics', []):
            if tid not in parents:
                errors.append(pid + ': unknown topic ' + str(tid))
        if p.get('ccf') and not all(p.get(k) for k in ('ccf_catalog', 'ccf_source', 'venue')):
            errors.append(pid + ': CCF needs venue/catalog/source')
        if pid in included and p.get('fulltext') != 'available':
            warnings.append(pid + ': fulltext pending')
        if p.get('fulltext_help'):
            if (pid not in included or p.get('fulltext') == 'available' or
                    p.get('reading') not in ('abstract', 'intro-related-method', 'deep')):
                errors.append(pid + ': download help requires a relevant, read paper without fulltext')
            attempts = p.get('fulltext_attempts')
            if not isinstance(attempts, list) or not attempts or any(
                    not isinstance(a, dict) or not all(a.get(k) for k in ('source', 'result', 'date'))
                    for a in attempts):
                errors.append(pid + ': download help requires dated source/result attempts')
        if pid in included and p.get('zotero', {}).get('status') != 'synced':
            warnings.append(pid + ': Zotero pending')
    pending_count = sum(p.get('decision') == 'pending' for p in papers)
    if pending_count:
        warnings.append(str(pending_count) + ': pending candidates remain in backend; not shown in map')
    for r in state.get('relations', []):
        if r.get('from') not in pids or r.get('to') not in pids:
            errors.append('relation has unknown endpoint')
        if r.get('verified') and not r.get('evidence'):
            errors.append('verified relation needs evidence')
        if r.get('verified') and (r.get('from') not in included or r.get('to') not in included):
            warnings.append('relation endpoint not included; not rendered')
    if state.get('coverage') == 'complete':
        if any(q.get('status') not in ('done', 'excluded') for q in queue):
            errors.append('complete coverage has unfinished queue')
        if any(p.get('decision') == 'pending' for p in papers):
            errors.append('complete coverage has pending candidates')
        if not all(state.get('gates', {}).get(g) for g in ('scope', 'seeds', 'taxonomy', 'final')):
            errors.append('complete coverage lacks discussion gates')
    return errors, warnings


def elem(parent, name, text=None, **attrs):
    child = ET.SubElement(parent, '{%s}%s' % (NS, name), attrs)
    child.text = text
    return child


def node(parent, ident, title, folded=False, link=None, note=None):
    topic = elem(parent, 'topic', id=ident)
    elem(topic, 'title', title)
    if folded:
        topic.set('branch', 'folded')
    if link:
        topic.set('{%s}href' % XLINK, link)
    if note:
        elem(elem(topic, 'notes'), 'plain', note)
    return topic


def children(topic):
    existing = topic.find('{%s}children/{%s}topics' % (NS, NS))
    return existing if existing is not None else elem(elem(topic, 'children'), 'topics', type='attached')


def export_run(path):
    path = Path(path)
    errors, warnings = check_run(path)
    if errors:
        raise ValueError('\n'.join(errors))
    state, papers, _ = load_run(path)
    revision = hashlib.sha256(b''.join((path / n).read_bytes() for n in
                              ('scope.md', 'papers.jsonl', 'queue.jsonl')) +
                              json.dumps({k: v for k, v in state.items() if k != 'exports'},
                                         sort_keys=True).encode()).hexdigest()[:12]
    root = ET.Element('{%s}xmap-content' % NS, {'version': '2.0'})
    sheet = elem(root, 'sheet', id='sheet-' + state['run_id'])
    elem(sheet, 'title', state['title'])
    status = '阶段成果' if state['coverage'] == 'complete' else '调研中'
    center = node(sheet, 'root', state['title'] + ' · ' + status + ' · ' + str(date.today()),
                  note='Revision: ' + revision + '\n' + '\n'.join(state.get('limitations', [])))
    center.set('structure-class', 'org.xmind.ui.logic.right')
    topics = {}

    def add_topic(t):
        if t['id'] in topics:
            return topics[t['id']]
        parent = center
        if t.get('parent'):
            parent = add_topic(next(x for x in state['topics'] if x['id'] == t['parent']))
        topics[t['id']] = node(children(parent), 't-' + t['id'], t['title'])
        return topics[t['id']]

    for t in state['topics']:
        add_topic(t)
    others, paper_nodes = {}, {}
    for p in papers:
        if p['decision'] != 'include':
            continue
        label = ' · '.join(str(v) for v in (p.get('short_title') or p['title'], p.get('year'),
                             p.get('venue'), ('CCF ' + p['ccf']) if p.get('ccf') else
                             ('预印本' if p.get('publication_status') == 'preprint' else '等级待核实'),
                             p.get('summary')) if v)
        if p.get('fulltext') != 'available':
            label += ' [需用户帮助下载]' if p.get('fulltext_help') else ' [待获取全文]'
        z = p.get('zotero', {})
        link = z.get('select_uri') if z.get('status') == 'synced' else p.get('url')
        for tid in dict.fromkeys(p['topics']):
            parent = topics[tid]
            if not p.get('key_paper'):
                if tid not in others:
                    others[tid] = node(children(parent), 'other-' + tid, '其他相关工作', folded=True)
                parent = others[tid]
            ident = 'p-' + hashlib.sha256((p['id'] + '\0' + tid).encode()).hexdigest()[:20]
            node(children(parent), ident, label, link=link,
                 note=p['title'] + '\n阅读：' + p.get('reading', 'pending') +
                      '\nZotero：' + z.get('status', 'pending') + '\n' + p.get('evidence', ''))
            paper_nodes.setdefault(p['id'], ident)
    rels = None
    for index, r in enumerate(state.get('relations', [])):
        if (r.get('verified') and r.get('kind') in ('improves', 'extends', 'derives') and
                r.get('from') in paper_nodes and r.get('to') in paper_nodes):
            if rels is None:
                rels = elem(sheet, 'relationships')
            rel = elem(rels, 'relationship', id='rel-' + str(index),
                       end1=paper_nodes[r['from']], end2=paper_nodes[r['to']])
            elem(rel, 'title', r.get('label') or r['kind'])
    content = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    ET.fromstring(content)
    manifest_ns = 'urn:xmind:xmap:xmlns:manifest:1.0'
    manifest = ET.Element('manifest', {'xmlns': manifest_ns})
    files = {'content.xml': content,
             'styles.xml': b'<?xml version="1.0"?><xmap-styles xmlns="urn:xmind:xmap:xmlns:style:2.0" version="2.0"/>',
             'meta.xml': b'<?xml version="1.0"?><meta xmlns="urn:xmind:xmap:xmlns:meta:2.0"/>'}
    for name in files:
        ET.SubElement(manifest, 'file-entry', {'full-path': name, 'media-type': 'text/xml'})
    files['META-INF/manifest.xml'] = ET.tostring(manifest, encoding='utf-8', xml_declaration=True)
    output = path / 'roadmap.xmind'
    fd, temp = tempfile.mkstemp(dir=path, suffix='.xmind')
    os.close(fd)
    try:
        with zipfile.ZipFile(temp, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, data in files.items():
                archive.writestr(name, data)
        with zipfile.ZipFile(temp) as archive:
            if archive.testzip():
                raise ValueError('invalid XMind zip')
        if output.exists():
            shutil.copy2(output, path / 'roadmap.previous.xmind')
        os.replace(temp, output)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    missing = ['# 待补全文\n'] + ['- ' + p['id'] + '：' + p['title'] + ' ' + p.get('url', '')
               for p in papers if p['decision'] == 'include' and p.get('fulltext') != 'available']
    atomic_write(path / 'pending-fulltext.md', ('\n'.join(missing) + '\n').encode('utf-8'))
    help_lines = ['# 需要用户帮助下载\n']
    for p in papers:
        if p['decision'] != 'include' or not p.get('fulltext_help'):
            continue
        help_lines.extend(['## ' + p['title'], '', p.get('url', ''),
                           '主题：' + '、'.join(next(t['title'] for t in state['topics'] if t['id'] == tid)
                                              for tid in p['topics']),
                           '相关性：' + p['reason'], '阅读层级：' + p['reading'], '已尝试来源：'])
        help_lines.extend('- ' + a['date'] + ' · ' + a['source'] + ' · ' + a['result']
                          for a in p['fulltext_attempts'])
        help_lines.append('')
    if len(help_lines) == 1:
        help_lines.append('暂无已记录获取尝试并确认需要用户协助的条目；不表示所有全文已取得。')
    atomic_write(path / 'download-help.md', ('\n'.join(help_lines) + '\n').encode('utf-8'))
    state['exports'] = dict(revision=revision, date=str(date.today()), structure_checked=True,
                            client_checked=False, warnings=warnings)
    write_json(path / 'state.json', state)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['init', 'check', 'export'])
    parser.add_argument('run', type=Path)
    parser.add_argument('--title', default='Literature roadmap')
    args = parser.parse_args()
    if args.command == 'init':
        init_run(args.run, args.title)
    elif args.command == 'export':
        print(export_run(args.run))
    else:
        errors, warnings = check_run(args.run)
        print(json.dumps(dict(errors=errors, warnings=warnings), ensure_ascii=False, indent=2))
        return bool(errors)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
