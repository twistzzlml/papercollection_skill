import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import roadmap


class RoadmapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.tmp.cleanup)
        self.run = Path(self.tmp.name) / '中文调研'
        roadmap.init_run(self.run, '反序列化')
        self.state = json.loads((self.run / 'state.json').read_text(encoding='utf-8'))
        self.state['topics'] = [{'id': 't1', 'title': '攻击生成', 'parent': None},
                                {'id': 't2', 'title': '防御', 'parent': None}]
        self.papers = [dict(id='p1', title='测试 & <论文>', year=2025, decision='include',
                            reason='直接相关', topics=['t1', 't2'], key_paper=True,
                            summary='构造与验证', url='https://example.org/p1',
                            reading='intro-related-method', fulltext='available',
                            venue='Test', publication_status='preprint', ccf=None),
                       dict(id='p2', title='小改进', decision='include', reason='相关',
                            topics=['t1'], key_paper=False, summary='增量贡献',
                            fulltext='missing', reading='abstract'),
                       dict(id='p3', title='待判断', decision='pending', topics=[])]
        self.save()

    def save(self):
        roadmap.write_json(self.run / 'state.json', self.state)
        roadmap.write_jsonl(self.run / 'papers.jsonl', self.papers)

    def test_init_never_overwrites_existing_run(self):
        before = (self.run / 'state.json').read_bytes()
        with self.assertRaises(FileExistsError):
            roadmap.init_run(self.run, '替换')
        self.assertEqual(before, (self.run / 'state.json').read_bytes())

    def test_export_preserves_unicode_multi_membership_and_pending(self):
        path = roadmap.export_run(self.run)
        with zipfile.ZipFile(path) as z:
            root = ET.fromstring(z.read('content.xml'))
            titles = [n.text for n in root.iter('{%s}title' % roadmap.NS)]
            self.assertEqual(sum('测试 & <论文>' in (x or '') for x in titles), 2)
            self.assertTrue(any('小改进' in (x or '') for x in titles))
            self.assertNotIn('待判断', titles)
            self.assertTrue(any(n.get('branch') == 'folded' for n in root.iter()))
            ids = [n.get('id') for n in root.iter() if n.get('id')]
            self.assertEqual(len(ids), len(set(ids)))
            self.assertIn('META-INF/manifest.xml', z.namelist())
        self.assertIn('小改进', (self.run / 'pending-fulltext.md').read_text(encoding='utf-8'))
        self.assertEqual(roadmap.read_jsonl(self.run / 'papers.jsonl'), self.papers)
        self.assertNotIn('待判断', (self.run / 'pending-fulltext.md').read_text(encoding='utf-8'))

    def test_download_help_requires_attempts_and_stays_in_topic(self):
        self.papers[1]['fulltext_help'] = True
        self.save()
        errors, _ = roadmap.check_run(self.run)
        self.assertTrue(any('attempts' in e for e in errors))
        self.papers[1]['fulltext_attempts'] = [dict(source='https://example.org/p2',
                                                  result='institution login required', date='2026-10-12')]
        self.save()
        path = roadmap.export_run(self.run)
        with zipfile.ZipFile(path) as z:
            root = ET.fromstring(z.read('content.xml'))
            topic = next(n for n in root.iter('{%s}topic' % roadmap.NS) if n.get('id') == 't-t1')
            titles = [n.text for n in topic.iter('{%s}title' % roadmap.NS)]
            self.assertTrue(any('小改进' in x and '需用户帮助下载' in x for x in titles))
        self.assertIn('https://example.org/p2', (self.run / 'download-help.md').read_text(encoding='utf-8'))
        self.papers[1]['fulltext'] = 'available'
        self.save()
        errors, _ = roadmap.check_run(self.run)
        self.assertTrue(any('without fulltext' in e for e in errors))

    def test_bad_taxonomy_does_not_replace_good_export(self):
        output = roadmap.export_run(self.run)
        before = output.read_bytes()
        self.state['topics'][0]['parent'] = 't2'
        self.state['topics'][1]['parent'] = 't1'
        self.save()
        with self.assertRaises(ValueError):
            roadmap.export_run(self.run)
        self.assertEqual(before, output.read_bytes())

    def test_missing_topic_and_duplicate_identity_rejected(self):
        self.papers[0]['topics'] = ['unknown']
        self.papers[1]['id'] = 'p1'
        self.save()
        errors, _ = roadmap.check_run(self.run)
        self.assertTrue(any('unknown' in e for e in errors))
        self.assertTrue(any('duplicate' in e for e in errors))

    def test_unproven_lineage_rejected(self):
        self.state['relations'] = [{'from': 'p1', 'to': 'p2', 'kind': 'improves',
                                    'verified': True, 'evidence': ''}]
        self.save()
        errors, _ = roadmap.check_run(self.run)
        self.assertTrue(any('evidence' in e for e in errors))

    def test_completion_with_open_queue_rejected(self):
        self.state['coverage'] = 'complete'
        self.save()
        roadmap.write_jsonl(self.run / 'queue.jsonl', [dict(id='q1', status='pending')])
        errors, _ = roadmap.check_run(self.run)
        self.assertTrue(any('queue' in e for e in errors))

    def test_ccf_grade_needs_catalog_evidence(self):
        self.papers[0]['ccf'] = 'A'
        self.save()
        errors, _ = roadmap.check_run(self.run)
        self.assertTrue(any('CCF' in e for e in errors))

    def test_malformed_state_is_rejected_before_export(self):
        self.state.pop('phase')
        self.state.pop('scope_version')
        self.state['topics'][0].pop('title')
        self.save()
        roadmap.write_jsonl(self.run / 'queue.jsonl', [dict(id='q1')])
        errors, _ = roadmap.check_run(self.run)
        for field in ('phase', 'scope_version', 'title', 'queue'):
            self.assertTrue(any(field in e for e in errors), field)


if __name__ == '__main__':
    unittest.main()
