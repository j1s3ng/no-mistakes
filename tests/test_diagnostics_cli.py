import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from no_mistakes.cli import main
from no_mistakes.hosts import SKILL_PATH, install


class DiagnosticCliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name)

    def invoke(self, project=None):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            status = main(['doctor', '--host', 'codex', '--project',
                           str(self.project if project is None else project)])
        return status, output.getvalue(), errors.getvalue()

    def snapshot(self):
        return {str(path.relative_to(self.project)): path.read_bytes()
                for path in self.project.rglob('*') if path.is_file()}

    def test_healthy_installation_returns_success_without_creating_memory(self):
        install(self.project, ['codex'])
        before = self.snapshot()
        status, output, errors = self.invoke()
        report = json.loads(output)
        self.assertEqual(status, 0)
        self.assertTrue(report['ok'])
        self.assertEqual(report['issues'], [])
        self.assertEqual(errors, '')
        self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.project / '.no-mistakes').exists())

    def test_findings_are_aggregated_and_exit_one_without_disclosing_file_text(self):
        install(self.project, ['codex'])
        reference = f'{SKILL_PATH}/references/web-research.md'
        (self.project / reference).unlink()
        (self.project / 'AGENTS.md').write_text('SYNTHETIC_PRIVATE_CANARY\n')
        before = self.snapshot()
        status, output, errors = self.invoke()
        report = json.loads(output)
        self.assertEqual(status, 1)
        self.assertFalse(report['ok'])
        self.assertTrue({reference, 'AGENTS.md'} <= {item['path'] for item in report['issues']})
        self.assertNotIn('SYNTHETIC_PRIVATE_CANARY', output + errors)
        self.assertEqual(self.snapshot(), before)

    def test_invalid_project_exits_two_without_creating_it(self):
        missing = self.project / 'does-not-exist'
        status, output, errors = self.invoke(missing)
        self.assertEqual(status, 2)
        self.assertEqual(output, '')
        self.assertIn('project', errors.lower())
        self.assertFalse(missing.exists())
