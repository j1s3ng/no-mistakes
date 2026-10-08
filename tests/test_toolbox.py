from copy import deepcopy
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import stat
import tempfile
import unittest

from no_mistakes.tool_catalog import get_tool, recommend
from no_mistakes.toolbox import build_proposal, validate_proposal, apply_proposal


TODAY = date(2026, 10, 8)


class ToolboxTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project = self.root / 'project'
        self.project.mkdir()

    def snapshot(self):
        entries = {}
        for path in self.root.rglob('*'):
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                value = ('symlink', str(path.readlink()))
            elif stat.S_ISDIR(mode):
                value = ('directory',)
            else:
                value = ('file', path.read_bytes())
            entries[str(path.relative_to(self.root))] = (stat.S_IMODE(mode), value)
        return entries

    def proposal(self, host='claude', tools=None, **kwargs):
        return build_proposal(
            tools if tools is not None else [get_tool('openai-docs')],
            host, self.project, 'Read official documentation for the current task',
            'project', today=TODAY, **kwargs)

    def rehash(self, proposal):
        unsigned = {key: value for key, value in proposal.items() if key != 'digest'}
        proposal['digest'] = hashlib.sha256(json.dumps(
            unsigned, ensure_ascii=False, sort_keys=True,
            separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()
        return proposal

    def rejected_without_changes(self, operation):
        before = self.snapshot()
        with self.assertRaises(ValueError):
            operation()
        self.assertEqual(self.snapshot(), before)

    def test_plan_and_validate_are_inert_and_preserve_input(self):
        tools = [get_tool('playwright'), get_tool('context7')]
        original = deepcopy(tools)
        before = self.snapshot()
        proposal = self.proposal(tools=tools)
        validate_proposal(proposal, today=TODAY)
        self.assertEqual(tools, original)
        self.assertEqual(self.snapshot(), before)
        self.assertIn('digest', proposal)
        self.assertEqual(proposal['scope'], 'project')

    def test_catalog_returns_independent_copies(self):
        tool = get_tool('playwright')
        tool['connection']['args'].append('--unsafe-example')
        self.assertNotIn('--unsafe-example', get_tool('playwright')['connection']['args'])

    def test_available_capabilities_suppress_duplicate_recommendations(self):
        result = recommend('research', available=['web-search', 'web-fetch', 'library-docs'])
        self.assertTrue(all(item['available'] for item in result['capabilities']))
        self.assertTrue(all(not item['optional_mcp_candidates'] for item in result['capabilities']))

    def test_decline_calls_confirmation_and_creates_nothing(self):
        proposal = self.proposal()
        calls = []
        before = self.snapshot()
        apply_proposal(proposal, lambda *args: calls.append(args) or False, today=TODAY)
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.snapshot(), before)

    def test_confirmation_exception_propagates_without_creating_configuration(self):
        proposal = self.proposal()
        calls = []
        def confirm(review):
            calls.append(review)
            raise RuntimeError('Confirmation UI failed')
        before = self.snapshot()
        with self.assertRaisesRegex(RuntimeError, 'Confirmation UI failed'):
            apply_proposal(proposal, confirm, today=TODAY)
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.snapshot(), before)

    def test_confirmation_creates_only_native_target_and_repeat_is_unchanged(self):
        proposal = self.proposal()
        calls = []
        apply_proposal(proposal, lambda *args: calls.append(args) or True, today=TODAY)
        self.assertEqual(len(calls), 1)
        target = self.project / '.mcp.json'
        self.assertTrue(target.is_file())
        document = json.loads(target.read_text())
        self.assertEqual(document['mcpServers']['openai-docs']['type'], 'http')
        self.assertEqual(document['mcpServers']['openai-docs']['url'], 'https://developers.openai.com/mcp')
        self.assertEqual({str(p.relative_to(self.project)) for p in self.project.rglob('*')}, {'.mcp.json'})
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
        before = self.snapshot()
        repeat_calls = []
        result = apply_proposal(proposal, lambda *args: repeat_calls.append(args) or True, today=TODAY)
        self.assertEqual(result['status'], 'unchanged')
        self.assertEqual(repeat_calls, [])
        self.assertEqual(self.snapshot(), before)

    def test_conflicting_existing_file_rejected_before_prompt(self):
        proposal = self.proposal()
        (self.project / '.mcp.json').write_text('{"mcpServers":{"existing":{}}}\n')
        calls = []
        self.rejected_without_changes(lambda: apply_proposal(
            proposal, lambda *args: calls.append(args) or True, today=TODAY))
        self.assertEqual(calls, [])

    def test_json_approval_field_cannot_bypass_confirmation(self):
        proposal = self.proposal()
        proposal['approved'] = True
        calls = []
        self.rejected_without_changes(lambda: apply_proposal(
            proposal, lambda *args: calls.append(args) or True, today=TODAY))
        self.assertEqual(calls, [])

    def test_truthy_values_are_not_user_confirmation(self):
        proposal = self.proposal()
        for verdict in ['yes', 1, {'approved': True}, None]:
            with self.subTest(verdict=verdict):
                calls = []
                before = self.snapshot()
                result = apply_proposal(proposal, lambda *args: calls.append(args) or verdict, today=TODAY)
                self.assertEqual(result['status'], 'declined')
                self.assertEqual(len(calls), 1)
                self.assertEqual(self.snapshot(), before)

    def test_digest_tamper_rejected_before_prompt(self):
        proposal = self.proposal()
        proposal['reason'] = 'A different undisclosed purpose'
        calls = []
        self.rejected_without_changes(lambda: apply_proposal(
            proposal, lambda *args: calls.append(args) or True, today=TODAY))
        self.assertEqual(calls, [])

    def test_recomputed_digest_does_not_authorize_inconsistent_native_fields(self):
        mutations = [
            ('target', '../outside.json'),
            ('config', '{"mcpServers":{"unreviewed":{"command":"arbitrary"}}}\n'),
            ('notice', 'This server was independently tested and approved'),
            ('schema_version', 2),
        ]
        for key, value in mutations:
            with self.subTest(field=key):
                proposal = self.proposal()
                proposal[key] = value
                self.rehash(proposal)
                calls = []
                self.rejected_without_changes(lambda: apply_proposal(
                    proposal, lambda *args: calls.append(args) or True, today=TODAY))
                self.assertEqual(calls, [])

    def test_changing_confirmation_copy_cannot_change_applied_configuration(self):
        proposal = self.proposal()
        calls = []
        def confirm(review):
            calls.append(review)
            review['config'] = 'Altered native configuration'
            return True
        self.rejected_without_changes(lambda: apply_proposal(proposal, confirm, today=TODAY))
        self.assertEqual(len(calls), 1)

    def test_custom_dossier_is_validated_and_kept_distinct_from_catalog(self):
        custom = get_tool('openai-docs')
        custom['id'] = 'reviewed-custom-docs'
        custom['name'] = 'Reviewed custom documentation service'
        custom['review']['maintainer'] = 'Example maintainer'
        custom['review']['source_urls'] = ['https://example.com/documentation']
        custom['connection']['url'] = 'https://example.com/mcp'
        proposal = self.proposal(tools=[custom])
        validate_proposal(proposal, today=TODAY)
        self.assertEqual(proposal['tools'][0], custom)
        native = json.loads(proposal['config'])['mcpServers']
        self.assertEqual(set(native), {'reviewed-custom-docs'})
        self.assertEqual(native['reviewed-custom-docs']['url'], 'https://example.com/mcp')
        self.assertEqual(get_tool('openai-docs')['connection']['url'], 'https://developers.openai.com/mcp')

    def test_native_hosts_render_transport_and_environment_syntax(self):
        before = self.snapshot()
        for host, target in [('claude', '.mcp.json'), ('cursor', '.cursor/mcp.json'),
                             ('gemini', '.gemini/settings.json'),
                             ('copilot-vscode', '.vscode/mcp.json'),
                             ('copilot-cli', '.mcp.json')]:
            with self.subTest(host=host):
                proposal = self.proposal(host, [get_tool('brave-search'), get_tool('context7')])
                validate_proposal(proposal, today=TODAY)
                self.assertEqual(proposal['target'], target)
                document = json.loads(proposal['config'])
                servers = document['servers' if host == 'copilot-vscode' else 'mcpServers']
                env_prefix = '${env:' if host in ('cursor', 'copilot-vscode') else '${'
                self.assertEqual(servers['brave-search']['env']['BRAVE_API_KEY'], env_prefix + 'BRAVE_API_KEY}')
                self.assertEqual(servers['context7']['headers']['Authorization'], 'Bearer ' + env_prefix + 'CONTEXT7_API_KEY}')
                self.assertEqual(servers['context7']['httpUrl' if host == 'gemini' else 'url'], 'https://mcp.context7.com/mcp')
                if host in ('claude', 'copilot-vscode'):
                    self.assertEqual(servers['brave-search']['type'], 'stdio')
                    self.assertEqual(servers['context7']['type'], 'http')
                if host == 'gemini':
                    self.assertIs(servers['brave-search']['trust'], False)
                    self.assertIs(servers['context7']['trust'], False)
                if host == 'copilot-cli':
                    self.assertEqual(servers['context7']['tools'], ['*'])
        codex = self.proposal('codex', [get_tool('brave-search'), get_tool('context7')])
        self.assertEqual(codex['target'], '.codex/config.toml')
        self.assertIn('env_vars = ["BRAVE_API_KEY"]', codex['config'])
        self.assertIn('bearer_token_env_var = "CONTEXT7_API_KEY"', codex['config'])
        self.assertNotIn('Bearer ${', codex['config'])
        self.assertEqual(self.snapshot(), before)

    def test_native_file_appearing_during_confirmation_is_preserved(self):
        proposal = self.proposal()
        calls = []
        target = self.project / '.mcp.json'
        def confirm(*args):
            calls.append(args)
            target.write_text('Concurrent user configuration\n')
            return True
        with self.assertRaises(ValueError):
            apply_proposal(proposal, confirm, today=TODAY)
        self.assertEqual(len(calls), 1)
        self.assertEqual(target.read_text(), 'Concurrent user configuration\n')
        self.assertEqual(list(self.project.iterdir()), [target])

    def test_parent_symlink_appearing_during_confirmation_cannot_escape_project(self):
        proposal = self.proposal(host='cursor')
        outside = self.root / 'outside-race'
        outside.mkdir()
        calls = []
        def confirm(review):
            calls.append(review)
            (self.project / '.cursor').symlink_to(outside, target_is_directory=True)
            return True
        with self.assertRaises(ValueError):
            apply_proposal(proposal, confirm, today=TODAY)
        self.assertEqual(len(calls), 1)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertTrue((self.project / '.cursor').is_symlink())

    def test_target_and_parent_symlinks_rejected_before_prompt(self):
        for host, relative in [('claude', '.mcp.json'), ('cursor', '.cursor')]:
            with self.subTest(host=host):
                proposal = self.proposal(host=host)
                outside = self.root / ('outside-' + host)
                if host == 'cursor':
                    outside.mkdir()
                else:
                    outside.write_text('Outside data\n')
                link = self.project / relative
                link.symlink_to(outside, target_is_directory=host == 'cursor')
                calls = []
                self.rejected_without_changes(lambda: apply_proposal(
                    proposal, lambda *args: calls.append(args) or True, today=TODAY))
                self.assertEqual(calls, [])
                link.unlink()

    def test_stale_and_future_research_rejected_without_changes(self):
        for checked_on in [TODAY - timedelta(days=31), TODAY + timedelta(days=1)]:
            with self.subTest(checked_on=checked_on):
                tool = get_tool('openai-docs')
                tool['review']['checked_on'] = checked_on.isoformat()
                self.rejected_without_changes(lambda: self.proposal(tools=[tool]))

    def test_thirty_day_review_remains_usable_but_duplicate_tools_are_rejected(self):
        tool = get_tool('openai-docs')
        tool['review']['checked_on'] = (TODAY - timedelta(days=30)).isoformat()
        before = self.snapshot()
        proposal = self.proposal(tools=[tool])
        validate_proposal(proposal, today=TODAY)
        self.assertEqual(self.snapshot(), before)
        self.rejected_without_changes(lambda: self.proposal(tools=[tool, deepcopy(tool)]))

    def test_custom_review_sources_cannot_embed_credentials(self):
        for source in ['https://example.com/docs?token=synthetic-secret',
                       'https://user:password@example.com/docs']:
            with self.subTest(source=source):
                tool = get_tool('openai-docs')
                tool['review']['source_urls'] = [source]
                self.rejected_without_changes(lambda: self.proposal(tools=[tool]))

    def test_proposal_expires_before_apply_without_prompt(self):
        proposal = self.proposal()
        calls = []
        self.rejected_without_changes(lambda: apply_proposal(
            proposal, lambda *args: calls.append(args) or True,
            today=TODAY + timedelta(days=31)))
        self.assertEqual(calls, [])

    def test_raw_credentials_mutable_packages_and_unsafe_urls_rejected(self):
        connections = [
            {'transport': 'http', 'url': 'https://user:password@example.com/mcp', 'headers': {}, 'token_env': None},
            {'transport': 'http', 'url': 'https://example.com/mcp?api_key=synthetic-secret', 'headers': {}, 'token_env': None},
            {'transport': 'http', 'url': 'http://example.com/mcp', 'headers': {}, 'token_env': None},
            {'transport': 'http', 'url': 'https://example.com/mcp', 'headers': {'Authorization': 'Bearer synthetic-secret'}, 'token_env': None},
            {'transport': 'stdio', 'command': 'npx', 'args': ['-y', '@playwright/mcp@latest'], 'env': {}, 'env_vars': []},
            {'transport': 'stdio', 'command': 'npx', 'args': ['-y', '@playwright/mcp'], 'env': {}, 'env_vars': []},
            {'transport': 'stdio', 'command': 'approved-server', 'args': [], 'env': {'API_KEY': 'synthetic-secret'}, 'env_vars': []},
        ]
        for connection in connections:
            with self.subTest(connection=connection):
                tool = get_tool('openai-docs')
                tool['connection'] = connection
                self.rejected_without_changes(lambda: self.proposal(tools=[tool]))

    def test_generic_proposal_cannot_apply_native_config(self):
        proposal = self.proposal(host='generic')
        calls = []
        self.rejected_without_changes(lambda: apply_proposal(
            proposal, lambda *args: calls.append(args) or True, today=TODAY))
        self.assertEqual(calls, [])

    def test_missing_project_is_not_created(self):
        missing = self.project / 'missing'
        self.rejected_without_changes(lambda: build_proposal(
            [get_tool('openai-docs')], 'claude', missing,
            'Read official documentation', 'project', today=TODAY))
        self.assertFalse(missing.exists())


if __name__ == '__main__':
    unittest.main()
