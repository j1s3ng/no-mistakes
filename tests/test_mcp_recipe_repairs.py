from datetime import date
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from no_mistakes.tool_catalog import get_tool
from no_mistakes.toolbox import build_proposal


TODAY = date(2026, 10, 8)


class MCPRecipeRepairTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)

    def proposal(self, host, tools):
        return build_proposal(tools, host, self.project, 'Verify the approved capability',
                              'project', today=TODAY)

    def test_github_auth_reference_is_rendered_without_resolving_secret_or_widening_tools(self):
        secret = 'SYNTHETIC_GITHUB_PAT_CANARY_35cd2'
        with patch.dict(os.environ, {'GITHUB_PAT_TOKEN': secret}):
            for host in ('codex', 'claude', 'cursor', 'gemini', 'copilot-vscode', 'copilot-cli'):
                with self.subTest(host=host):
                    proposal = self.proposal(host, [get_tool('github')])
                    config = proposal['config']
                    self.assertNotIn(secret, json.dumps(proposal))
                    if host == 'codex':
                        self.assertIn('bearer_token_env_var = "GITHUB_PAT_TOKEN"', config)
                        self.assertIn('"X-MCP-Readonly" = "true"', config)
                        self.assertIn('"X-MCP-Lockdown" = "true"', config)
                        self.assertIn('"X-MCP-Toolsets" = "repos,issues,pull_requests"', config)
                    else:
                        document = json.loads(config)
                        server = document['servers' if host == 'copilot-vscode' else 'mcpServers']['github']
                        reference = ('${env:GITHUB_PAT_TOKEN}' if host in ('cursor', 'copilot-vscode')
                                     else '${GITHUB_PAT_TOKEN}')
                        self.assertEqual(server['headers']['Authorization'], 'Bearer ' + reference)
                        self.assertEqual(server['headers']['X-MCP-Readonly'], 'true')
                        self.assertEqual(server['headers']['X-MCP-Lockdown'], 'true')
                        self.assertEqual(server['headers']['X-MCP-Toolsets'], 'repos,issues,pull_requests')
        self.assertEqual(list(self.project.iterdir()), [])

    def test_cursor_config_explicitly_distinguishes_local_and_remote_transports(self):
        proposal = self.proposal('cursor', [get_tool('playwright'), get_tool('openai-docs')])
        servers = json.loads(proposal['config'])['mcpServers']
        self.assertEqual(servers['playwright']['type'], 'stdio')
        self.assertEqual(servers['playwright']['command'], 'npx')
        self.assertNotIn('url', servers['playwright'])
        self.assertEqual(servers['openai-docs']['type'], 'http')
        self.assertEqual(servers['openai-docs']['url'], 'https://developers.openai.com/mcp')
        self.assertNotIn('command', servers['openai-docs'])

    @unittest.skipUnless(os.name == 'posix' and hasattr(os, 'mkfifo'), 'POSIX FIFO required')
    def test_apply_existing_file_replaced_with_fifo_does_not_block_or_request_consent(self):
        program = textwrap.dedent('''\
            from datetime import date
            import os
            from pathlib import Path
            import sys
            from unittest.mock import patch
            from no_mistakes.tool_catalog import get_tool
            from no_mistakes.toolbox import apply_proposal, build_proposal

            project = Path(sys.argv[1])
            proposal = build_proposal([get_tool('openai-docs')], 'claude', project,
                'Verify a read-only tool', 'project', today=date(2026, 10, 8))
            target = Path(proposal['project']) / '.mcp.json'
            target.write_text(proposal['config'], encoding='utf-8')
            original_open = os.open
            calls = []
            def replace_with_fifo(path, flags, *args, **kwargs):
                if Path(path) == target:
                    target.unlink()
                    os.mkfifo(target)
                return original_open(path, flags, *args, **kwargs)
            with patch('no_mistakes.toolbox.os.open', side_effect=replace_with_fifo):
                try:
                    apply_proposal(proposal, lambda review: calls.append(review) or True,
                                   today=date(2026, 10, 8))
                except ValueError as error:
                    assert 'regular file' in str(error), str(error)
                else:
                    raise SystemExit('Unexpected acceptance of replacement FIFO')
            assert not calls, 'Unsafe configuration reached confirmation'
            print('Replacement FIFO rejected before confirmation')
            ''')
        result = subprocess.run([sys.executable, '-c', program, str(self.project)],
                                stdin=subprocess.DEVNULL, capture_output=True,
                                text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'Replacement FIFO rejected before confirmation')
        self.assertEqual(result.stderr, '')


if __name__ == '__main__':
    unittest.main()
