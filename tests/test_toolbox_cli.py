import contextlib
from datetime import date
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from no_mistakes.cli import main
from no_mistakes.tool_catalog import get_tool, list_tools, recommend
from no_mistakes.toolbox import build_proposal


class ToolboxCliTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / 'project'
        self.project.mkdir()
        self.tool = get_tool('brave-search')
        self.tool['id'] = 'synthetic-search'
        self.tool['name'] = 'Synthetic test fixture, not a real server recommendation'
        self.tool['review']['checked_on'] = date.today().isoformat()
        self.tool['review']['maintainer'] = 'Synthetic test fixture'
        self.tool['review']['source_urls'] = ['https://example.com/synthetic-docs']
        self.spec = self.root / 'spec.json'
        self.spec.write_text(json.dumps(self.tool), encoding='utf-8')
        self.proposal = build_proposal([self.tool], 'claude', self.project,
                                       'Synthetic public search test', 'This synthetic project only')
        self.saved = self.root / 'proposal.json'
        self.saved.write_text(json.dumps(self.proposal), encoding='utf-8')

    def invoke(self, *arguments, stdin=None):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            if stdin is None:
                status = main(['toolbox', *arguments])
            else:
                with patch('sys.stdin', stdin):
                    status = main(['toolbox', *arguments])
        return status, output.getvalue(), errors.getvalue()

    def inventory(self):
        return {str(path.relative_to(self.project)):
                ('link', os.readlink(path)) if path.is_symlink() else
                ('directory', stat.S_IMODE(path.stat().st_mode)) if path.is_dir() else
                ('file', stat.S_IMODE(path.stat().st_mode), path.read_bytes())
                for path in self.project.rglob('*')}

    def test_catalog_and_capability_recommendation_do_not_enable_tools(self):
        before = self.inventory()
        status, output, errors = self.invoke('list', '--profile', 'web')
        self.assertEqual(status, 0, errors)
        self.assertIn('playwright', {tool['id'] for tool in json.loads(output)['tools']})
        status, output, errors = self.invoke('recommend', '--profile', 'web', '--available', 'browser')
        self.assertEqual(status, 0, errors)
        rows = {row['capability']: row for row in json.loads(output)['capabilities']}
        self.assertTrue(rows['browser']['available'])
        self.assertEqual(rows['browser']['optional_mcp_candidates'], [])
        self.assertFalse(rows['tests']['available'])
        self.assertEqual(self.inventory(), before)

    def test_custom_plan_is_inert_and_does_not_resolve_secret_environment(self):
        with patch.dict(os.environ, {'BRAVE_API_KEY': 'SYNTHETIC_CREDENTIAL_CANARY'}):
            status, output, errors = self.invoke('plan', '--spec', str(self.spec),
                '--host', 'copilot-vscode', '--project', str(self.project),
                '--reason', 'Synthetic search test', '--scope', 'Only public synthetic queries')
        self.assertEqual(status, 0, errors)
        proposal = json.loads(output)
        self.assertIn('${env:BRAVE_API_KEY}', proposal['config'])
        self.assertNotIn('SYNTHETIC_CREDENTIAL_CANARY', output + errors)
        self.assertEqual(proposal['scope'], 'Only public synthetic queries')
        self.assertEqual(self.inventory(), {})

    def test_curated_plan_supports_multiple_selected_tools(self):
        with patch('no_mistakes.toolbox._today', return_value=date(2026, 10, 8)):
            status, output, errors = self.invoke('plan', '--tool', 'playwright', '--tool', 'github',
                '--host', 'codex', '--project', str(self.project),
                '--reason', 'Synthetic web project', '--scope', 'Synthetic test project')
        self.assertEqual(status, 0, errors)
        result = json.loads(output)
        self.assertEqual({tool['id'] for tool in result['tools']}, {'playwright', 'github'})
        self.assertIn('@playwright/mcp@0.0.83', result['config'])
        self.assertIn('X-MCP-Readonly', result['config'])
        self.assertEqual(self.inventory(), {})

    def test_show_produces_exact_inert_config(self):
        status, output, errors = self.invoke('show', str(self.saved), '--config-only')
        self.assertEqual(status, 0, errors)
        self.assertEqual(output, self.proposal['config'])
        self.assertEqual(self.inventory(), {})

    def test_inspection_shows_original_research_without_claiming_execution(self):
        status, output, errors = self.invoke('inspect', 'playwright')
        self.assertEqual(status, 0, errors)
        dossier = json.loads(output)
        self.assertEqual(dossier['review']['status'], 'inspected_not_executed')
        self.assertEqual(dossier['review']['checked_on'], '2026-10-08')
        self.assertTrue(dossier['review']['source_urls'])
        self.assertEqual(self.inventory(), {})

    def test_piped_yes_or_digest_cannot_supply_interactive_consent(self):
        piped = io.StringIO('enable ' + self.proposal['digest'][:12] + '\n')
        status, output, errors = self.invoke('apply', str(self.saved), stdin=piped)
        self.assertEqual(status, 2)
        self.assertEqual(output, '')
        self.assertIn('interactive', errors)
        self.assertEqual(self.inventory(), {})

    def test_interactive_decline_does_not_write_and_stdout_remains_json(self):
        terminal = io.StringIO()
        with patch.object(terminal, 'isatty', return_value=True), patch('builtins.input', return_value='yes'):
            status, output, errors = self.invoke('apply', str(self.saved), stdin=terminal)
        self.assertEqual(status, 1, errors)
        self.assertEqual(json.loads(output)['status'], 'declined')
        self.assertIn(self.proposal['digest'][:12], errors)
        self.assertIn('data_flow', errors)
        self.assertIn('cost', errors)
        self.assertEqual(self.inventory(), {})

    def test_interactive_exact_confirmation_creates_only_selected_config(self):
        terminal = io.StringIO()
        answer = 'enable ' + self.proposal['digest'][:12]
        with patch.object(terminal, 'isatty', return_value=True), patch('builtins.input', return_value=answer):
            status, output, errors = self.invoke('apply', str(self.saved), stdin=terminal)
        self.assertEqual(status, 0, errors)
        self.assertEqual(json.loads(output)['status'], 'created')
        target = self.project / '.mcp.json'
        self.assertEqual(target.read_text(), self.proposal['config'])
        self.assertEqual(set(self.inventory()), {'.mcp.json'})
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)

    def test_existing_user_config_blocks_before_prompt_and_preserves_everything(self):
        existing = self.project / '.mcp.json'
        existing.write_bytes(b'// Synthetic private existing JSONC config\n')
        before = self.inventory()
        with patch('builtins.input') as ask:
            status, output, errors = self.invoke('apply', str(self.saved), stdin=io.StringIO())
        self.assertEqual(status, 2)
        self.assertIn('manually merge', errors)
        self.assertNotIn('Synthetic private existing', errors + output)
        self.assertEqual(ask.call_count, 0)
        self.assertEqual(self.inventory(), before)

    def test_serialized_approval_does_not_grant_consent(self):
        self.proposal['approved'] = True
        self.saved.write_text(json.dumps(self.proposal), encoding='utf-8')
        status, output, errors = self.invoke('apply', str(self.saved), stdin=io.StringIO())
        self.assertEqual(status, 2)
        self.assertEqual(output, '')
        self.assertNotIn('interactive', errors)
        self.assertEqual(self.inventory(), {})

    def test_ambiguous_duplicate_keys_and_overlarge_documents_fail_before_writes(self):
        for content in ('{"id":"first","id":"second"}', ' ' * 262_145):
            with self.subTest(content_size=len(content)):
                self.spec.write_text(content, encoding='utf-8')
                status, output, errors = self.invoke('plan', '--spec', str(self.spec), '--host', 'claude',
                    '--project', str(self.project), '--reason', 'Synthetic check', '--scope', 'Synthetic scope')
                self.assertEqual(status, 2)
                self.assertEqual(output, '')
                self.assertEqual(self.inventory(), {})

    def test_empty_selection_and_incomplete_research_do_not_create_config(self):
        for selected in ([], ['--spec', str(self.spec)]):
            with self.subTest(selected=selected):
                incomplete = dict(self.tool)
                incomplete.pop('review')
                self.spec.write_text(json.dumps(incomplete), encoding='utf-8')
                status, output, errors = self.invoke('plan', *selected, '--host', 'claude',
                    '--project', str(self.project), '--reason', 'Synthetic check', '--scope', 'Synthetic scope')
                self.assertEqual(status, 2)
                self.assertEqual(output, '')
                self.assertEqual(self.inventory(), {})

    def test_reviewed_package_version_must_match_the_command_being_proposed(self):
        self.tool['review']['version'] = '9.9.9'
        self.spec.write_text(json.dumps(self.tool), encoding='utf-8')
        status, output, errors = self.invoke('plan', '--spec', str(self.spec), '--host', 'claude',
            '--project', str(self.project), '--reason', 'Synthetic mismatch', '--scope', 'Synthetic scope')
        self.assertEqual(status, 2)
        self.assertIn('matching review.version', errors)
        self.assertEqual(output, '')
        self.assertEqual(self.inventory(), {})


class CapabilityRecommendationTests(unittest.TestCase):
    def test_exported_catalog_values_do_not_mutate_future_research(self):
        listed = list_tools()
        listed['tools'][0]['capabilities'].append('synthetic-unwanted')
        self.assertNotIn('synthetic-unwanted', get_tool(listed['tools'][0]['id'])['capabilities'])

    def test_available_capabilities_require_explicit_valid_sequence(self):
        for value in ('browser', None, ['unknown'], [{}], iter(['browser'])):
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(ValueError):
                    recommend('web', value)
        rows = recommend('data', ['files', 'data'])['capabilities']
        self.assertTrue(next(row for row in rows if row['capability'] == 'data')['available'])


if __name__ == '__main__':
    unittest.main()
