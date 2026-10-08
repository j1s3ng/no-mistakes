from contextlib import ExitStack
from copy import deepcopy
from datetime import date, timedelta
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import urllib.request

from no_mistakes.tool_catalog import get_tool
from no_mistakes.toolbox import build_proposal
from no_mistakes.tool_readiness import check_readiness


TODAY = date(2026, 10, 8)


class ToolReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project = self.root / 'project'
        self.project.mkdir()

    def proposal(self, host='claude', tools=None):
        return build_proposal(
            tools if tools is not None else [get_tool('openai-docs')],
            host, self.project, 'Use the reviewed tool for this task', 'project', today=TODAY)

    def config(self, proposal, content=None):
        target = self.project / proposal['target']
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(proposal['config'].encode() if content is None else content)
        return target

    def custom(self, command):
        tool = get_tool('playwright')
        tool['id'] = 'custom-server'
        tool['connection'] = {
            'transport': 'stdio', 'command': command, 'args': [], 'env': {}, 'env_vars': []}
        return tool

    def executable(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('#!/bin/sh\nexit 73\n')
        path.chmod(0o700)
        return path

    def test_missing_config_does_not_create_it(self):
        proposal = self.proposal()
        original = deepcopy(proposal)
        result = check_readiness(proposal, today=TODAY)
        self.assertEqual(result['config']['status'], 'missing')
        self.assertFalse(result['local_ready'])
        self.assertEqual(list(self.project.iterdir()), [])
        self.assertEqual(proposal, original)
        self.assertEqual((result['project'], result['host'], result['digest']),
                         (proposal['project'], 'claude', proposal['digest']))

    def test_exact_http_config_only_proves_local_checklist(self):
        proposal = self.proposal()
        self.config(proposal)
        result = check_readiness(proposal, today=TODAY)
        self.assertEqual(result['config']['status'], 'matches_proposal')
        self.assertTrue(result['local_ready'])
        self.assertEqual(result['tools'][0]['executables'], [])
        self.assertEqual(result['tools'][0]['runtime_status'], 'not_checked')
        self.assertEqual(result['tools'][0]['authentication_status'], 'not_checked')
        self.assertEqual(result['tools'][0]['smoke_status'], 'not_run')
        self.assertIn('host may use a different environment', result['notice'])
        self.assertIn('runtime_verification_required', [item['code'] for item in result['issues']])

    def test_all_native_hosts_can_compare_their_own_exact_bytes(self):
        for host in ('codex', 'claude', 'cursor', 'gemini', 'copilot-vscode', 'copilot-cli'):
            with self.subTest(host=host):
                proposal = self.proposal(host=host)
                self.config(proposal)
                self.assertTrue(check_readiness(proposal, today=TODAY)['local_ready'])

    def test_conflicting_private_config_is_preserved_without_content_output(self):
        proposal = self.proposal()
        secret = b'PRIVATE_CONFIG_CANARY_30ba7\n'
        target = self.config(proposal, secret)
        result = check_readiness(proposal, today=TODAY)
        self.assertEqual(result['config']['status'], 'differs_manual_review')
        self.assertFalse(result['local_ready'])
        self.assertNotIn(secret.decode().strip(), json.dumps(result))
        self.assertEqual(target.read_bytes(), secret)

    def test_semantically_equivalent_config_still_requires_manual_review(self):
        proposal = self.proposal()
        self.config(proposal, json.dumps(json.loads(proposal['config'])).encode())
        result = check_readiness(proposal, today=TODAY)
        self.assertEqual(result['config']['status'], 'differs_manual_review')
        self.assertFalse(result['local_ready'])

    def test_npx_checks_launcher_node_and_npm_without_running_versions(self):
        proposal = self.proposal(tools=[get_tool('playwright')])
        self.config(proposal)
        with patch('no_mistakes.tool_readiness.shutil.which',
                   side_effect=lambda name: '/not-reported/bin/' + name):
            result = check_readiness(proposal, today=TODAY)
        self.assertEqual(result['tools'][0]['executables'], [
            {'name': 'npx', 'status': 'found'}, {'name': 'node', 'status': 'found'},
            {'name': 'npm', 'status': 'found'}])
        self.assertTrue(result['local_ready'])
        self.assertEqual(result['tools'][0]['prerequisites'], proposal['tools'][0]['prerequisites'])
        self.assertNotIn('/not-reported/bin', json.dumps(result))

    def test_missing_any_npx_prerequisite_prevents_local_readiness(self):
        proposal = self.proposal(tools=[get_tool('playwright')])
        self.config(proposal)
        for missing in ('npx', 'node', 'npm'):
            with self.subTest(missing=missing), patch(
                    'no_mistakes.tool_readiness.shutil.which',
                    side_effect=lambda name: None if name == missing else '/found/' + name):
                result = check_readiness(proposal, today=TODAY)
                self.assertFalse(result['local_ready'])
                self.assertIn({'name': missing, 'status': 'missing'},
                              result['tools'][0]['executables'])

    def test_custom_relative_executable_uses_proposal_project_not_cwd(self):
        self.executable(self.project / 'bin' / 'reviewed-server')
        proposal = self.proposal(tools=[self.custom('bin/reviewed-server')])
        self.config(proposal)
        # The normal test cwd is the source checkout, which has no such file.
        self.assertFalse((Path.cwd() / 'bin' / 'reviewed-server').exists())
        result = check_readiness(proposal, today=TODAY)
        self.assertEqual(result['tools'][0]['executables'],
                         [{'name': 'reviewed-server', 'status': 'found'}])
        self.assertTrue(result['local_ready'])

    def test_dot_relative_executable_is_not_looked_up_in_current_directory(self):
        self.executable(self.project / 'local-server')
        proposal = self.proposal(tools=[self.custom('./local-server')])
        self.config(proposal)
        self.assertTrue(check_readiness(proposal, today=TODAY)['local_ready'])

    def test_absolute_custom_executable_path_is_not_reported_or_executed(self):
        executable = self.executable(self.root / 'private-tools' / 'reviewed-server')
        proposal = self.proposal(tools=[self.custom(str(executable))])
        self.config(proposal)
        result = check_readiness(proposal, today=TODAY)
        self.assertTrue(result['local_ready'])
        self.assertEqual(result['tools'][0]['executables'],
                         [{'name': 'reviewed-server', 'status': 'found'}])
        self.assertNotIn(str(executable), json.dumps(result))

    def test_nonexecutable_custom_file_is_missing(self):
        executable = self.project / 'server'
        executable.write_text('not executable')
        executable.chmod(0o600)
        proposal = self.proposal(tools=[self.custom('./server')])
        self.config(proposal)
        result = check_readiness(proposal, today=TODAY)
        self.assertFalse(result['local_ready'])
        self.assertEqual(result['tools'][0]['executables'], [{'name': 'server', 'status': 'missing'}])

    def test_http_credentials_presence_never_exposes_value_or_claims_authentication(self):
        proposal = self.proposal(tools=[get_tool('context7')])
        self.config(proposal)
        secret = 'PRIVATE_ENV_CANARY_f8e20'
        with patch.dict(os.environ, {'CONTEXT7_API_KEY': secret}):
            result = check_readiness(proposal, today=TODAY)
        self.assertTrue(result['local_ready'])
        self.assertEqual(result['tools'][0]['credentials'],
                         [{'name': 'CONTEXT7_API_KEY', 'status': 'present'}])
        self.assertEqual(result['tools'][0]['authentication_status'], 'not_checked')
        self.assertNotIn(secret, json.dumps(result))

    def test_missing_empty_and_whitespace_credentials_are_missing(self):
        proposal = self.proposal(tools=[get_tool('context7')])
        self.config(proposal)
        for values in ({}, {'CONTEXT7_API_KEY': ''}, {'CONTEXT7_API_KEY': ' \t\n'}):
            with self.subTest(values=values), patch.dict(os.environ, values, clear=True):
                result = check_readiness(proposal, today=TODAY)
                self.assertFalse(result['local_ready'])
                self.assertEqual(result['tools'][0]['credentials'],
                                 [{'name': 'CONTEXT7_API_KEY', 'status': 'missing'}])

    def test_stdio_credentials_are_checked_separately_from_literal_flags(self):
        proposal = self.proposal(tools=[get_tool('brave-search')])
        self.config(proposal)
        with patch.dict(os.environ, {'BRAVE_API_KEY': 'PRESENT_CANARY'}, clear=True), patch(
                'no_mistakes.tool_readiness.shutil.which', return_value='/not-disclosed/bin'):
            result = check_readiness(proposal, today=TODAY)
        self.assertEqual(result['tools'][0]['credentials'],
                         [{'name': 'BRAVE_API_KEY', 'status': 'present'}])
        self.assertNotIn('PRESENT_CANARY', json.dumps(result))
        self.assertTrue(result['local_ready'])

    def test_generic_host_needs_manual_setup_even_when_local_requirements_exist(self):
        result = check_readiness(self.proposal(host='generic'), today=TODAY)
        self.assertEqual(result['config']['status'], 'manual_host_setup')
        self.assertFalse(result['local_ready'])
        self.assertEqual(list(self.project.iterdir()), [])

    @unittest.skipUnless(hasattr(os, 'symlink'), 'symlinks unavailable')
    def test_final_symlink_and_parent_symlink_are_not_read(self):
        for host, is_parent in (('claude', False), ('cursor', True)):
            with self.subTest(host=host):
                proposal = self.proposal(host=host)
                outside = self.root / ('outside-' + host)
                if is_parent:
                    outside.mkdir()
                    (outside / 'mcp.json').write_text('PRIVATE_OUTSIDE_CANARY')
                    link = self.project / '.cursor'
                    link.symlink_to(outside, target_is_directory=True)
                else:
                    outside.write_text('PRIVATE_OUTSIDE_CANARY')
                    link = self.project / '.mcp.json'
                    link.symlink_to(outside)
                try:
                    with patch('no_mistakes.tool_readiness.os.open',
                               side_effect=AssertionError('Unsafe path was opened')):
                        result = check_readiness(proposal, today=TODAY)
                    self.assertEqual(result['config']['status'], 'unsafe_path')
                    self.assertFalse(result['local_ready'])
                    self.assertNotIn('PRIVATE_OUTSIDE_CANARY', json.dumps(result))
                finally:
                    link.unlink()

    def test_directory_configuration_is_unsafe(self):
        proposal = self.proposal()
        (self.project / proposal['target']).mkdir()
        result = check_readiness(proposal, today=TODAY)
        self.assertEqual(result['config']['status'], 'unsafe_path')
        self.assertFalse(result['local_ready'])

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'FIFOs unavailable')
    def test_fifo_configuration_is_rejected_before_open(self):
        proposal = self.proposal()
        os.mkfifo(self.project / proposal['target'])
        with patch('no_mistakes.tool_readiness.os.open',
                   side_effect=AssertionError('FIFO was opened')):
            result = check_readiness(proposal, today=TODAY)
        self.assertEqual(result['config']['status'], 'unsafe_path')
        self.assertFalse(result['local_ready'])

    def test_unreadable_configuration_does_not_leak_exception_text(self):
        proposal = self.proposal()
        self.config(proposal)
        with patch('no_mistakes.tool_readiness.os.open',
                   side_effect=PermissionError('PRIVATE_EXCEPTION_CANARY')):
            result = check_readiness(proposal, today=TODAY)
        self.assertEqual(result['config']['status'], 'unreadable')
        self.assertFalse(result['local_ready'])
        self.assertNotIn('PRIVATE_EXCEPTION_CANARY', json.dumps(result))

    def test_configuration_read_is_bounded_by_expected_bytes_plus_one(self):
        proposal = self.proposal()
        self.config(proposal, b'x' * (1024 * 1024))
        requests = []
        original_fdopen = os.fdopen

        class ReadProbe:
            def __init__(self, stream):
                self.stream = stream

            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.stream.close()

            def fileno(self):
                return self.stream.fileno()

            def read(self, size):
                requests.append(size)
                return self.stream.read(size)

        with patch('no_mistakes.tool_readiness.os.fdopen',
                   side_effect=lambda *args: ReadProbe(original_fdopen(*args))):
            result = check_readiness(proposal, today=TODAY)
        self.assertEqual(requests, [len(proposal['config'].encode('utf-8')) + 1])
        self.assertEqual(result['config']['status'], 'differs_manual_review')

    def test_readiness_does_not_launch_network_write_or_mutate_environment(self):
        proposal = self.proposal(tools=[get_tool('playwright'), get_tool('context7')])
        target = self.config(proposal)
        original_bytes = target.read_bytes()
        original_open = os.open
        calls = []

        def readonly_open(path, flags, *args, **kwargs):
            self.assertFalse(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC))
            calls.append(flags)
            return original_open(path, flags, *args, **kwargs)

        with patch.dict(os.environ, {'CONTEXT7_API_KEY': 'BOUNDARY_ENV_CANARY'}):
            environment = dict(os.environ)
            with ExitStack() as stack:
                for owner, name in ((subprocess, 'Popen'), (subprocess, 'run'),
                                    (socket, 'socket'), (socket, 'create_connection'),
                                    (urllib.request, 'urlopen'), (Path, 'write_bytes'),
                                    (Path, 'write_text'), (os, 'mkdir'), (os, 'unlink'),
                                    (os, 'rename'), (os, 'replace')):
                    stack.enter_context(patch.object(owner, name, side_effect=AssertionError(
                        'Forbidden operation: ' + name)))
                stack.enter_context(patch('no_mistakes.tool_readiness.os.open',
                                          side_effect=readonly_open))
                result = check_readiness(proposal, today=TODAY)
            self.assertEqual(dict(os.environ), environment)
        self.assertEqual(len(calls), 1)
        self.assertNotIn('BOUNDARY_ENV_CANARY', json.dumps(result))
        self.assertEqual(target.read_bytes(), original_bytes)
        self.assertEqual(list(self.project.iterdir()), [target])

    def test_invalid_and_stale_proposals_fail_before_observation(self):
        proposal = self.proposal()
        tampered = deepcopy(proposal)
        tampered['reason'] = 'Changed purpose'
        forged = deepcopy(proposal)
        forged['config'] = 'Unreviewed native configuration'
        unsigned = {key: value for key, value in forged.items() if key != 'digest'}
        forged['digest'] = hashlib.sha256(json.dumps(unsigned, ensure_ascii=False,
            sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        for candidate, today in ((tampered, TODAY), (forged, TODAY),
                                 (proposal, TODAY + timedelta(days=31))):
            with self.subTest(today=today), patch(
                    'no_mistakes.tool_readiness._config_status',
                    side_effect=AssertionError('Invalid proposal was observed')):
                with self.assertRaises(ValueError):
                    check_readiness(candidate, today=today)

    def test_executable_observation_errors_require_manual_check_without_error_output(self):
        proposal = self.proposal(tools=[self.custom('reviewed-server')])
        self.config(proposal)
        with patch('no_mistakes.tool_readiness.shutil.which',
                   side_effect=OSError('PRIVATE_EXECUTABLE_ERROR_CANARY')):
            result = check_readiness(proposal, today=TODAY)
        self.assertEqual(result['tools'][0]['executables'],
                         [{'name': 'reviewed-server', 'status': 'manual_check'}])
        self.assertFalse(result['local_ready'])
        self.assertNotIn('PRIVATE_EXECUTABLE_ERROR_CANARY', json.dumps(result))


if __name__ == '__main__':
    unittest.main()
