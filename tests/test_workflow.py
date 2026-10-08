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

    def test_correction_cannot_move_intent_between_project_scopes(self):
        original = remember(self.root, 'Keep the public API', 'user:1', 'project:A', 'explicit')
        before = (self.root / 'memory.json').read_bytes()
        with self.assertRaises(ValueError):
            remember(self.root, 'Use a new API', 'user:2', 'project:B', 'confirmed', original['id'])
        self.assertEqual((self.root / 'memory.json').read_bytes(), before)
        self.assertEqual([entry['id'] for entry in context(self.root, '', 'project:A')], [original['id']])
        self.assertEqual(context(self.root, '', 'project:B'), [])

    def test_invalid_programmatic_memory_input_does_not_create_storage(self):
        valid = dict(text='A preference', source='user:1', scope='project:A', kind='explicit')
        for invalid in ({'text': None}, {'source': 1}, {'scope': ' '}, {'kind': 'guessed'},
                        {'kind': None}, {'supersedes': ''}, {'supersedes': True}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                remember(self.root, **{**valid, **invalid})
            self.assertFalse(self.root.exists())

    def test_duplicate_memory_ids_are_rejected_without_rewriting_data(self):
        original = remember(self.root, 'A preference', 'user:1', 'project:A', 'explicit')
        path = self.root / 'memory.json'
        path.write_text(json.dumps([original, {**original, 'text': 'Conflicting preference'}]))
        before = path.read_bytes()
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['--memory-dir', str(self.root), 'context']), 2)
        self.assertEqual(path.read_bytes(), before)

    def test_corrupt_present_correction_links_are_rejected_without_writes(self):
        def entry(key, scope='private-project-A', **links):
            return dict(id=key, text='Sensitive synthetic summary', source='private-source',
                        scope=scope, kind='explicit', created_at='2026-10-08T00:00:00Z',
                        **links)

        cases = [
            ('self-predecessor', [entry('private-first', supersedes='private-first')],
             'same entry'),
            ('self-successor', [entry('private-first', superseded_by='private-first')],
             'same entry'),
            ('cross-scope', [entry('private-first', superseded_by='private-second'),
                             entry('private-second', 'private-project-B',
                                   supersedes='private-first')], 'same scope'),
            ('missing-forward-reciprocal', [entry('private-first', supersedes='private-second'),
                                            entry('private-second')], 'reciprocal'),
            ('missing-backward-reciprocal', [entry('private-first', superseded_by='private-second'),
                                             entry('private-second')], 'reciprocal'),
            ('conflicting-reciprocal', [entry('private-first', superseded_by='private-second'),
                                        entry('private-second', supersedes='private-third'),
                                        entry('private-third', superseded_by='private-second')],
             'reciprocal'),
            ('cycle', [entry('private-first', supersedes='private-third',
                             superseded_by='private-second'),
                       entry('private-second', supersedes='private-first',
                             superseded_by='private-third'),
                       entry('private-third', supersedes='private-second',
                             superseded_by='private-first')], 'cycle'),
        ]
        self.root.mkdir()
        path = self.root / 'memory.json'
        for name, records, reason in cases:
            with self.subTest(name=name):
                path.write_text(json.dumps(records), encoding='utf-8')
                before = path.read_bytes()
                with self.assertRaisesRegex(ValueError, reason):
                    read_memory(self.root)
                errors = io.StringIO()
                output = io.StringIO()
                with contextlib.redirect_stderr(errors), contextlib.redirect_stdout(output):
                    status = main(['--memory-dir', str(self.root), 'remember', 'New preference',
                                   '--source', 'user:new', '--scope', 'project:new',
                                   '--kind', 'explicit'])
                self.assertEqual(status, 2)
                self.assertEqual(output.getvalue(), '')
                self.assertEqual(path.read_bytes(), before)
                self.assertNotIn('Traceback', errors.getvalue())
                for private_value in ('private-first', 'private-second', 'private-third',
                                      'private-project-A', 'private-project-B', 'private-source',
                                      'Sensitive synthetic summary'):
                    self.assertNotIn(private_value, errors.getvalue())

    def test_long_correction_chain_and_independent_scope_are_valid(self):
        # A valid history longer than Python's usual recursion limit must remain readable.
        records = []
        for index in range(1200):
            record = dict(id=f'entry-{index}', text='Preference', source='user:1',
                          scope='project:A', kind='explicit', created_at='2026-10-08T00:00:00Z')
            if index:
                record['supersedes'] = f'entry-{index - 1}'
            if index < 1199:
                record['superseded_by'] = f'entry-{index + 1}'
            records.append(record)
        records.append(dict(id='other-scope', text='Preference', source='user:2',
                            scope='project:B', kind='explicit', created_at='2026-10-08T00:00:00Z'))
        self.root.mkdir()
        path = self.root / 'memory.json'
        # Read newest-first so validation traverses the entire history in one pass.
        path.write_text(json.dumps(list(reversed(records))), encoding='utf-8')
        before = path.read_bytes()
        self.assertEqual(len(read_memory(self.root)), 1201)
        self.assertEqual([e['id'] for e in context(self.root, '', 'project:A')], ['entry-1199'])
        self.assertEqual([e['id'] for e in context(self.root, '', 'project:B')], ['other-scope'])
        self.assertEqual(path.read_bytes(), before)

    def test_absent_correction_references_preserve_inactive_history(self):
        self.root.mkdir()
        records = [
            dict(id='old', text='Old preference', source='user:1', scope='project:A',
                 kind='explicit', created_at='2026-10-08T00:00:00Z', superseded_by='missing-new'),
            dict(id='new', text='New preference', source='user:2', scope='project:A',
                 kind='confirmed', created_at='2026-10-08T00:00:00Z', supersedes='missing-old'),
            dict(id='tombstoned', text='Obsolete preference', source='user:3', scope='project:A',
                 kind='explicit', created_at='2026-10-08T00:00:00Z',
                 superseded_by='deleted-correction'),
        ]
        path = self.root / 'memory.json'
        path.write_text(json.dumps(records), encoding='utf-8')
        before = path.read_bytes()
        self.assertEqual(read_memory(self.root), records)
        self.assertEqual([e['id'] for e in context(self.root, '')], ['new'])
        self.assertEqual(path.read_bytes(), before)

    def test_graph_preserves_node_order_edges_and_shared_sources(self):
        first = remember(self.root, 'First preference', 'user:1', 'project:A', 'explicit')
        second = remember(self.root, 'Second preference', 'user:1', 'project:A', 'confirmed')
        correction = remember(self.root, 'Revised preference', 'user:2', 'project:A',
                              'explicit', first['id'])
        result = graph(self.root)
        self.assertEqual([node['id'] for node in result['nodes']],
                         [first['id'], 'source:user:1', second['id'], correction['id'], 'source:user:2'])
        self.assertEqual(result['edges'], [
            {'from': first['id'], 'to': 'source:user:1', 'relation': 'supported_by', 'basis': 'explicit'},
            {'from': second['id'], 'to': 'source:user:1', 'relation': 'supported_by', 'basis': 'confirmed'},
            {'from': correction['id'], 'to': 'source:user:2', 'relation': 'supported_by', 'basis': 'explicit'},
            {'from': correction['id'], 'to': first['id'], 'relation': 'supersedes', 'basis': 'explicit'},
        ])

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

    def test_forget_each_chain_position_preserves_current_intent_and_other_scopes(self):
        for position in range(3):
            with self.subTest(position=position):
                root = self.root / str(position)
                first = remember(root, 'First preference', 'user:1', 'project:A', 'explicit')
                middle = remember(root, 'Middle preference', 'user:2', 'project:A',
                                  'confirmed', first['id'])
                latest = remember(root, 'Latest preference', 'user:3', 'project:A',
                                  'explicit', middle['id'])
                other = remember(root, 'Unrelated preference', 'user:4', 'project:B', 'explicit')
                deleted = (first, middle, latest)[position]
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(['--memory-dir', str(root), 'forget', deleted['id']]), 0)
                remaining = read_memory(root)
                self.assertEqual(len(remaining), 3)
                self.assertEqual([e['id'] for e in context(root, '', 'project:A')],
                                 [] if position == 2 else [latest['id']])
                self.assertEqual(context(root, '', 'project:B'), [other])
                serialized = (root / 'memory.json').read_text(encoding='utf-8')
                self.assertNotIn(deleted['id'], serialized)
                self.assertNotIn(deleted['text'], serialized)
                self.assertNotIn(deleted['id'], json.dumps(graph(root)))
                if position:
                    predecessor = next(e for e in remaining
                                       if e['id'] == (first, middle)[position - 1]['id'])
                    self.assertEqual(predecessor['superseded_by'], 'deleted-correction')

    def test_deleted_correction_marker_does_not_resolve_to_an_unrelated_live_id(self):
        for scope in ('project:A', 'project:B'):
            with self.subTest(scope=scope):
                root = self.root / scope[-1]
                old = remember(root, 'Old preference', 'user:1', 'project:A', 'explicit')
                new = remember(root, 'New preference', 'user:2', 'project:A',
                               'confirmed', old['id'])
                unrelated = dict(id='deleted-correction', text='Independent preference',
                                 source='user:3', scope=scope, kind='explicit',
                                 created_at='2026-10-08T00:00:00Z')
                path = root / 'memory.json'
                path.write_text(json.dumps(read_memory(root) + [unrelated]), encoding='utf-8')
                self.assertEqual(len(read_memory(root)), 3)
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(['--memory-dir', str(root), 'forget', new['id']]), 0)
                self.assertEqual(len(read_memory(root)), 2)
                self.assertEqual([entry['id'] for entry in context(root, '', scope)],
                                 ['deleted-correction'])
                self.assertNotIn(old['id'], [entry['id'] for entry in context(root, '')])
                self.assertNotIn(new['id'], json.dumps(graph(root)))
                following = remember(root, 'Another preference', 'user:4', 'project:A',
                                     'explicit')
                self.assertIn(following['id'], [entry['id'] for entry in context(root, '')])


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

    def test_invalid_final_artifact_is_rejected_independently(self):
        for artifact in ('', ' ', None, 42):
            with self.subTest(artifact=artifact):
                report = self.report()
                report['final_review']['artifact'] = artifact
                self.assertTrue(check_report(report))

    def test_each_final_review_aspect_requires_evidence_independently(self):
        for aspect in ('goal_alignment', 'system_fit', 'side_effects'):
            for evidence in ('', ' ', None, 42):
                with self.subTest(aspect=aspect, evidence=evidence):
                    report = self.report()
                    report['final_review'][aspect]['evidence'] = evidence
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
