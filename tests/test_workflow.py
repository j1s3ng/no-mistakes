import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from no_mistakes.cli import activation, check_report, context, graph, main, read_memory, remember


class TriggerTests(unittest.TestCase):
    def test_suffixes(self):
        for suffix in ('no mistakes', 'NO MISTAKES.', 'No Mistakes.  \n'):
            self.assertEqual(activation('Fix it. ' + suffix), {'active': True, 'task': 'Fix it.'})

    def test_nontriggers(self):
        for prompt in ('no mistakes please', 'Fix it. no mistakes!', 'Fix it. no mistakes..',
                       'Fix it. ohno mistakes', 'Mention "no mistakes"', 'no mistakes. more'):
            self.assertFalse(activation(prompt)['active'], prompt)

    def test_empty_task(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(['prepare', 'no mistakes.']), 0)
        self.assertTrue(json.loads(output.getvalue())['needs_task'])


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'private'

    def test_correction_and_provenance(self):
        old = remember(self.root, 'Use dependencies', 'user:1', 'a', 'explicit')
        new = remember(self.root, 'Avoid dependencies', 'user:2', 'a', 'confirmed', old['id'])
        self.assertEqual([e['id'] for e in context(self.root, 'dependencies')], [new['id']])
        self.assertTrue(any(e['relation'] == 'supersedes' for e in graph(self.root)['edges']))
        self.assertEqual(len(read_memory(self.root)), 2)

    def test_scope_and_inference(self):
        remember(self.root, 'Maybe use Python', 'user:1', 'a', 'inferred')
        remember(self.root, 'Use Python', 'user:2', 'b', 'explicit')
        result = context(self.root, 'Python', 'a')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['kind'], 'inferred')
        self.assertEqual(context(self.root, 'unrelated'), [])

    def test_bad_correction(self):
        with self.assertRaises(ValueError):
            remember(self.root, 'Preference', 'user:1', 'a', 'explicit', 'missing')
        self.assertFalse(self.root.exists())

    def test_forget_correction_does_not_revive_old_intent(self):
        old = remember(self.root, 'Use dependencies', 'user:1', 'a', 'explicit')
        new = remember(self.root, 'Avoid dependencies', 'user:2', 'a', 'explicit', old['id'])
        with contextlib.redirect_stdout(io.StringIO()):
            main(['--memory-dir', str(self.root), 'forget', new['id']])
        self.assertEqual(context(self.root, 'dependencies'), [])
        self.assertNotIn(new['id'], (self.root / 'memory.json').read_text())
        self.assertNotIn('Avoid dependencies', (self.root / 'memory.json').read_text())

    def test_forget_original_unlinks_graph(self):
        old = remember(self.root, 'Old private summary', 'user:1', 'a', 'explicit')
        new = remember(self.root, 'Current summary', 'user:2', 'a', 'explicit', old['id'])
        with contextlib.redirect_stdout(io.StringIO()):
            main(['--memory-dir', str(self.root), 'forget', old['id']])
        self.assertEqual([e['id'] for e in context(self.root, '')], [new['id']])
        self.assertNotIn(old['id'], json.dumps(graph(self.root)))


class ReportTests(unittest.TestCase):
    def report(self):
        return {'intent': 'Fix retries', 'criteria': [
            {'text': 'Retry succeeds', 'status': 'passed', 'evidence': 'test_retry: passed'}],
            'claims': [], 'limitations': []}

    def test_complete(self):
        self.assertEqual(check_report(self.report()), [])

    def test_failures_and_unsupported_claims(self):
        report = self.report()
        report['criteria'][0]['status'] = 'failed'
        report['claims'] = [{'text': 'External fact', 'status': 'verified', 'evidence': ''}]
        self.assertEqual(len(check_report(report)), 2)

    def test_malformed(self):
        for report in (None, {}, {'intent': 'x', 'criteria': [None], 'claims': [3], 'limitations': []}):
            self.assertTrue(check_report(report))

    def test_module_exit_code(self):
        result = subprocess.run([sys.executable, '-m', 'no_mistakes', 'check',
                                 'docs/report.example.json'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(json.loads(result.stdout)['complete'])


if __name__ == '__main__':
    unittest.main()
