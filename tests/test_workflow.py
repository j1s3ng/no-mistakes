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

    def test_malformed_memory_returns_input_error_without_traceback(self):
        self.root.mkdir()
        for records in ([None], [{}], [{'id': 'one', 'text': None}]):
            (self.root / 'memory.json').write_text(json.dumps(records))
            errors = io.StringIO()
            with contextlib.redirect_stderr(errors):
                status = main(['--memory-dir', str(self.root), 'context'])
            self.assertEqual(status, 2)
            self.assertNotIn('Traceback', errors.getvalue())

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
            'claims': [], 'limitations': [],
            'iteration_summary': {'passes': 1, 'stop_reason': 'complete'},
            'final_review': {
                'artifact': 'final checkout diff after retry fix',
                'goal_alignment': {'status': 'passed', 'evidence': 'Compared retry behavior with request'},
                'system_fit': {'status': 'passed', 'evidence': 'Inspected checkout flow and unchanged API'},
                'side_effects': {'status': 'passed', 'evidence': 'Duplicate-charge integration check passed'},
            }}

    def test_complete(self):
        self.assertEqual(check_report(self.report()), [])

    def test_failures_and_unsupported_claims(self):
        report = self.report()
        report['criteria'][0]['status'] = 'failed'
        report['claims'] = [{'text': 'External fact', 'status': 'verified', 'evidence': ''}]
        self.assertEqual(len(check_report(report)), 2)

    def test_green_tests_without_final_review_do_not_complete(self):
        report = self.report()
        del report['final_review']
        self.assertTrue(check_report(report))

    def test_system_mismatch_blocks_completion_despite_green_tests(self):
        report = self.report()
        report['final_review']['system_fit'] = {
            'status': 'failed', 'evidence': 'Deployment config still uses the old callback interface',
        }
        self.assertTrue(check_report(report))

    def test_empty_final_review_evidence_and_unknown_artifact_are_rejected(self):
        report = self.report()
        report['final_review']['side_effects']['evidence'] = ' '
        report['final_review']['artifact'] = ''
        self.assertTrue(check_report(report))

    def test_iteration_count_requires_valid_values_within_recorded_allowance(self):
        for passes in (0, 11, True, 1.5, '2'):
            report = self.report()
            report['iteration_summary']['passes'] = passes
            self.assertTrue(check_report(report), passes)
        report = self.report()
        report['iteration_summary']['passes'] = 10
        self.assertEqual(check_report(report), [])

    def test_explicit_continuation_allows_only_its_recorded_extension(self):
        report = self.report()
        report['iteration_summary'].update(
            passes=12,
            continuations=[{'additional_passes': 2, 'approval': 'user continuation reply: message 14'}],
        )
        self.assertEqual(check_report(report), [])
        report['iteration_summary']['passes'] = 13
        self.assertTrue(check_report(report))
        report['iteration_summary']['continuations'].append(
            {'additional_passes': 1, 'approval': 'user continuation reply: message 18'})
        self.assertEqual(check_report(report), [])

    def test_invalid_or_missing_approval_cannot_extend_allowance(self):
        invalid = [None, {}, {'additional_passes': 2, 'approval': ' '},
                   {'additional_passes': 11, 'approval': 'user:14'},
                   {'additional_passes': True, 'approval': 'user:14'},
                   {'additional_passes': '2', 'approval': 'user:14'},
                   {'additional_passes': 0, 'approval': 'user:14'}]
        for record in invalid:
            report = self.report()
            report['iteration_summary'].update(passes=11, continuations=[record])
            self.assertTrue(check_report(report), record)
        report = self.report()
        report['iteration_summary']['continuations'] = 'approved'
        self.assertTrue(check_report(report))

    def test_one_approval_cannot_grant_two_extensions(self):
        report = self.report()
        report['iteration_summary'].update(
            passes=21,
            continuations=[
                {'additional_passes': 10, 'approval': 'user reply:14'},
                {'additional_passes': 10, 'approval': '  user reply:14  '},
            ],
        )
        self.assertTrue(check_report(report))
        report['iteration_summary']['continuations'][1]['approval'] = 'user reply:18'
        self.assertEqual(check_report(report), [])

    def test_budget_exhaustion_and_context_stop_are_not_completion(self):
        for reason in ('pass_limit', 'context_limit', 'needs_input', 'no_progress', 'resource_limit', 'stalled'):
            report = self.report()
            report['iteration_summary']['stop_reason'] = reason
            self.assertTrue(check_report(report), reason)

    def test_missing_iteration_record_does_not_complete(self):
        report = self.report()
        del report['iteration_summary']
        self.assertTrue(check_report(report))

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
