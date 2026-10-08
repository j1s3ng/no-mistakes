import contextlib
import io
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from no_mistakes.cli import main
from no_mistakes.hosts import BEGIN, END, HOSTS, MANIFEST_PATH, SKILL_PATH, install, skill_payload


class HostInstallTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name) / 'project'
        self.project.mkdir()

    def snapshot(self):
        return {str(path.relative_to(self.project)): path.read_bytes()
                for path in self.project.rglob('*') if path.is_file()}

    def write(self, relative, content):
        target = self.project / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content if isinstance(content, bytes) else content.encode('utf-8'))
        return target

    def assert_no_changes_after_failure(self, hosts, error=ValueError):
        before = self.snapshot()
        with self.assertRaises(error):
            install(self.project, hosts)
        self.assertEqual(self.snapshot(), before)

    def install_with_retired_reference(self, hosts=('codex',)):
        payload = dict(skill_payload())
        payload['references/retired.md'] = b'# Retired workflow guidance\n'
        with patch('no_mistakes.hosts.skill_payload', return_value=payload):
            install(self.project, hosts)
        return f'{SKILL_PATH}/references/retired.md'

    def test_dry_run_reports_changes_without_creating_files_or_directories(self):
        result = install(self.project, list(HOSTS), dry_run=True)
        self.assertTrue(result['dry_run'])
        self.assertEqual(result['hosts'], list(HOSTS))
        self.assertTrue(result['files'])
        self.assertTrue(all(item['action'] == 'create' for item in result['files']))
        self.assertEqual(list(self.project.iterdir()), [])

    def test_all_host_profiles_share_complete_skill_and_have_native_routes(self):
        install(self.project, list(HOSTS))
        payload = skill_payload()
        self.assertIn('SKILL.md', payload)
        self.assertIn('references/web-research.md', payload)
        self.assertIn('references/adaptive-flow.md', payload)
        for relative, content in payload.items():
            self.assertEqual((self.project / SKILL_PATH / relative).read_bytes(), content)
        for relative in set(HOSTS.values()):
            route = (self.project / relative).read_text()
            self.assertEqual(route.count(BEGIN), 1, relative)
            self.assertEqual(route.count(END), 1, relative)
            self.assertIn(f'{SKILL_PATH}/SKILL.md', route)
            self.assertIn('`no mistakes`', route)
            self.assertIn('`no mistakes.`', route)
            self.assertIn('case-insensitive', route)
        cursor = (self.project / HOSTS['cursor']).read_text()
        self.assertTrue(cursor.startswith('---\n'))
        self.assertIn('alwaysApply: true', cursor)
        command = (self.project / '.claude/commands/no-mistakes.md').read_text()
        self.assertTrue(command.startswith('---\n'))
        self.assertIn('$ARGUMENTS', command)
        self.assertIn(f'{SKILL_PATH}/SKILL.md', command)
        manifest = json.loads((self.project / MANIFEST_PATH).read_text())
        self.assertEqual(manifest['version'], 1)
        self.assertIn(f'{SKILL_PATH}/SKILL.md', manifest['files'])
        self.assertNotIn('AGENTS.md', manifest['files'])

    def test_selecting_one_host_does_not_write_other_host_profiles(self):
        for host in HOSTS:
            with self.subTest(host=host), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                install(root, [host])
                expected = {f'{SKILL_PATH}/{name}' for name in skill_payload()}
                expected.update((MANIFEST_PATH, HOSTS[host]))
                if host == 'claude':
                    expected.add('.claude/commands/no-mistakes.md')
                actual = {str(path.relative_to(root)) for path in root.rglob('*') if path.is_file()}
                self.assertEqual(actual, expected)

    def test_reordered_duplicate_and_subset_installs_are_idempotent(self):
        install(self.project, list(HOSTS))
        original = self.snapshot()
        result = install(self.project, ['generic', 'claude', 'codex', 'claude', 'cursor',
                                        'copilot', 'gemini'])
        self.assertEqual(result['hosts'].count('claude'), 1)
        self.assertTrue(all(item['action'] == 'unchanged' for item in result['files']))
        self.assertEqual(self.snapshot(), original)
        result = install(self.project, ['claude'])
        self.assertTrue(all(item['action'] == 'unchanged' for item in result['files']))
        self.assertEqual(self.snapshot(), original)

    def test_adding_hosts_preserves_earlier_ownership_and_routes(self):
        install(self.project, ['claude'])
        command = (self.project / '.claude/commands/no-mistakes.md').read_bytes()
        install(self.project, ['cursor', 'copilot'])
        install(self.project, ['claude'])
        self.assertEqual((self.project / '.claude/commands/no-mistakes.md').read_bytes(), command)
        manifest = json.loads((self.project / MANIFEST_PATH).read_text())
        self.assertIn('.claude/commands/no-mistakes.md', manifest['files'])
        self.assertIn(HOSTS['cursor'], manifest['files'])

    def test_skill_upgrade_updates_owned_files_and_keeps_project_instructions(self):
        self.write('AGENTS.md', '# Existing project conventions\n')
        install(self.project, ['codex'])
        updated = dict(skill_payload())
        updated['SKILL.md'] += b'\nUpdated workflow guidance.\n'
        updated['references/new-guide.md'] = b'# New supporting reference\n'
        with patch('no_mistakes.hosts.skill_payload', return_value=updated):
            result = install(self.project, ['codex'])
            actions = {item['path']: item['action'] for item in result['files']}
            self.assertEqual(actions[f'{SKILL_PATH}/SKILL.md'], 'update')
            self.assertEqual(actions[f'{SKILL_PATH}/references/new-guide.md'], 'create')
            self.assertEqual((self.project / SKILL_PATH / 'SKILL.md').read_bytes(), updated['SKILL.md'])
            self.assertTrue((self.project / 'AGENTS.md').read_text().startswith('# Existing project conventions\n'))
            again = install(self.project, ['codex'])
            self.assertTrue(all(item['action'] == 'unchanged' for item in again['files']))

    def test_retired_skill_file_dry_run_then_deletion_preserves_unowned_files(self):
        retired = self.install_with_retired_reference()
        extra = self.write(f'{SKILL_PATH}/references/local-guide.md', '# Local guide\n')
        before = self.snapshot()
        preview = install(self.project, ['codex'], dry_run=True)
        actions = {item['path']: item['action'] for item in preview['files']}
        self.assertEqual(actions[retired], 'delete')
        self.assertEqual(actions[MANIFEST_PATH], 'update')
        self.assertEqual(self.snapshot(), before)

        result = install(self.project, ['codex'])
        self.assertIn({'path': retired, 'action': 'delete'}, result['files'])
        self.assertFalse((self.project / retired).exists())
        manifest = json.loads((self.project / MANIFEST_PATH).read_text())
        self.assertNotIn(retired, manifest['files'])
        self.assertEqual(extra.read_bytes(), b'# Local guide\n')
        self.assertTrue(extra.parent.is_dir())
        again = install(self.project, ['codex'])
        self.assertTrue(all(item['action'] == 'unchanged' for item in again['files']))

    def test_missing_retired_skill_file_is_removed_from_manifest(self):
        retired = self.install_with_retired_reference()
        (self.project / retired).unlink()
        result = install(self.project, ['codex'])
        manifest = json.loads((self.project / MANIFEST_PATH).read_text())
        self.assertNotIn(retired, manifest['files'])
        self.assertNotIn(retired, {item['path'] for item in result['files']})
        self.assertTrue((self.project / retired).parent.is_dir())

    def test_modified_retired_skill_file_rejects_upgrade_before_any_writes(self):
        retired = self.install_with_retired_reference()
        self.write(retired, '# Local edits to retired guidance\n')
        self.assert_no_changes_after_failure(['codex', 'copilot', 'claude'])
        self.assertFalse((self.project / '.github').exists())
        self.assertFalse((self.project / 'CLAUDE.md').exists())

    def test_late_host_conflict_prevents_retired_file_deletion(self):
        retired = self.install_with_retired_reference()
        self.write('CLAUDE.md', BEGIN + '\nmissing end marker\n')
        self.assert_no_changes_after_failure(['codex', 'copilot', 'claude'])
        self.assertTrue((self.project / retired).is_file())
        self.assertFalse((self.project / '.github').exists())

    def test_retiring_skill_file_preserves_unselected_native_adapters(self):
        retired = self.install_with_retired_reference(('claude', 'cursor'))
        command = self.write('.claude/commands/no-mistakes.md', '# Local command customization\n')
        cursor = (self.project / HOSTS['cursor']).read_bytes()
        owned_before = json.loads((self.project / MANIFEST_PATH).read_text())['files']
        install(self.project, ['codex'])
        owned_after = json.loads((self.project / MANIFEST_PATH).read_text())['files']
        self.assertFalse((self.project / retired).exists())
        self.assertEqual(command.read_bytes(), b'# Local command customization\n')
        self.assertEqual((self.project / HOSTS['cursor']).read_bytes(), cursor)
        for relative in ('.claude/commands/no-mistakes.md', HOSTS['cursor']):
            self.assertEqual(owned_after[relative], owned_before[relative])

    def test_existing_project_instructions_are_preserved_for_each_routing_file(self):
        for relative in ('AGENTS.md', 'CLAUDE.md', 'GEMINI.md', '.github/copilot-instructions.md'):
            self.write(relative, '# Existing instructions\nKeep the existing behavior.\n')
        install(self.project, ['codex', 'copilot', 'claude', 'gemini'])
        for relative in ('AGENTS.md', 'CLAUDE.md', 'GEMINI.md', '.github/copilot-instructions.md'):
            content = (self.project / relative).read_text()
            self.assertTrue(content.startswith('# Existing instructions\nKeep the existing behavior.\n'))
            self.assertEqual(content.count(BEGIN), 1)

    def test_managed_block_updates_preserve_surrounding_bytes_and_crlf(self):
        prefix = '# Existing café\r\n\r\n'.encode('utf-8')
        suffix = '\r\n\r\n## After\r\nKeep this too.\r\n'.encode('utf-8')
        self.write('AGENTS.md', prefix + BEGIN.encode() + b'\r\nobsolete route\r\n' + END.encode() + suffix)
        install(self.project, ['codex', 'generic'])
        result = (self.project / 'AGENTS.md').read_bytes()
        self.assertTrue(result.startswith(prefix))
        self.assertTrue(result.endswith(suffix))
        self.assertNotIn(b'obsolete route', result)
        self.assertNotIn(b'\n', result.replace(b'\r\n', b''))
        before = self.snapshot()
        install(self.project, ['codex'])
        self.assertEqual(self.snapshot(), before)

    def test_existing_file_mode_survives_atomic_routing_update(self):
        target = self.write('AGENTS.md', '# Private project rules\n')
        target.chmod(0o640)
        install(self.project, ['codex'])
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o640)

    def test_unowned_canonical_skill_is_not_overwritten_even_if_identical(self):
        self.write(f'{SKILL_PATH}/SKILL.md', skill_payload()['SKILL.md'])
        self.assert_no_changes_after_failure(['codex'])

    def test_locally_modified_owned_skill_is_not_overwritten(self):
        install(self.project, ['codex'])
        self.write(f'{SKILL_PATH}/SKILL.md', '# Local skill customization\n')
        self.assert_no_changes_after_failure(['codex'])

    def test_unowned_native_adapters_are_not_overwritten(self):
        for host, relative in (('claude', '.claude/commands/no-mistakes.md'),
                               ('cursor', HOSTS['cursor'])):
            with self.subTest(host=host), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                target = root / relative
                target.parent.mkdir(parents=True)
                target.write_text('User adapter\n')
                with self.assertRaises(ValueError):
                    install(root, [host])
                self.assertEqual(target.read_text(), 'User adapter\n')
                self.assertFalse((root / SKILL_PATH).exists())

    def test_modified_owned_native_adapters_are_not_overwritten(self):
        install(self.project, ['claude', 'cursor'])
        for host, relative in (('claude', '.claude/commands/no-mistakes.md'),
                               ('cursor', HOSTS['cursor'])):
            with self.subTest(host=host):
                target = self.project / relative
                previous = target.read_bytes()
                target.write_bytes(b'User customization\n')
                self.assert_no_changes_after_failure([host])
                target.write_bytes(previous)

    def test_malformed_manifests_are_rejected_before_writing(self):
        records = ['not json', '[]', '{}', '{"version": true, "files": {}}',
                   '{"version": 2, "files": {}}', '{"version": 1, "files": []}',
                   json.dumps({'version': 1, 'files': {f'{SKILL_PATH}/SKILL.md': 'invalid'}}),
                   json.dumps({'version': 1, 'files': {'AGENTS.md': '0' * 64}}),
                   json.dumps({'version': 1, 'files': {MANIFEST_PATH: '0' * 64}}),
                   json.dumps({'version': 1, 'files': {f'{SKILL_PATH}//SKILL.md': '0' * 64}}),
                   json.dumps({'version': 1, 'files': {f'{SKILL_PATH}/./SKILL.md': '0' * 64}}),
                   json.dumps({'version': 1, 'files': {f'{SKILL_PATH}/../../outside.md': '0' * 64}})]
        for record in records:
            with self.subTest(record=record):
                self.write(MANIFEST_PATH, record)
                self.assert_no_changes_after_failure(['codex'])

    def test_malformed_routing_markers_are_rejected(self):
        records = [BEGIN, END, END + '\n' + BEGIN,
                   BEGIN + '\n' + BEGIN + '\n' + END,
                   BEGIN + '\n' + END + '\n' + END,
                   'prefix ' + BEGIN + '\n' + END,
                   BEGIN + '\n' + END + ' suffix']
        for record in records:
            with self.subTest(record=record):
                self.write('AGENTS.md', record)
                self.assert_no_changes_after_failure(['codex'])

    def test_late_host_conflict_preflights_all_writes(self):
        self.write('AGENTS.md', '# Existing instructions\n')
        self.write('CLAUDE.md', BEGIN + '\nmissing end marker\n')
        self.assert_no_changes_after_failure(['codex', 'copilot', 'claude'])
        self.assertFalse((self.project / '.agents').exists())
        self.assertFalse((self.project / '.github').exists())

    def test_existing_install_stays_unchanged_when_later_host_conflicts(self):
        install(self.project, ['codex'])
        self.write('CLAUDE.md', END + '\n')
        self.assert_no_changes_after_failure(['codex', 'copilot', 'claude'])

    def test_target_symlinks_are_refused_without_modifying_destination(self):
        outside = Path(self.temporary.name) / 'outside.md'
        outside.write_text('# Outside rules\n')
        (self.project / 'AGENTS.md').symlink_to(outside)
        with self.assertRaises(ValueError):
            install(self.project, ['codex'])
        self.assertTrue((self.project / 'AGENTS.md').is_symlink())
        self.assertEqual(outside.read_text(), '# Outside rules\n')
        self.assertFalse((self.project / '.agents').exists())

    def test_dangling_target_symlinks_are_refused(self):
        outside = Path(self.temporary.name) / 'missing.md'
        (self.project / 'AGENTS.md').symlink_to(outside)
        with self.assertRaises(ValueError):
            install(self.project, ['codex'])
        self.assertFalse(outside.exists())
        self.assertFalse((self.project / '.agents').exists())

    def test_parent_symlinks_for_shared_skill_and_host_rules_are_refused(self):
        for parent, host in (('.agents', 'codex'), ('.github', 'copilot'),
                             ('.claude', 'claude'), ('.cursor', 'cursor')):
            with self.subTest(parent=parent), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / 'project'
                outside = Path(directory) / 'outside'
                root.mkdir()
                outside.mkdir()
                (root / parent).symlink_to(outside, target_is_directory=True)
                with self.assertRaises(ValueError):
                    install(root, [host])
                self.assertEqual(list(outside.iterdir()), [])
                self.assertEqual(list(root.iterdir()), [root / parent])

    def test_directory_targets_and_file_ancestors_are_refused(self):
        (self.project / 'AGENTS.md').mkdir()
        self.assert_no_changes_after_failure(['codex'])
        (self.project / 'AGENTS.md').rmdir()
        self.write('.github', 'file, not directory\n')
        self.assert_no_changes_after_failure(['codex', 'copilot'])

    def test_invalid_hosts_and_dry_run_type_have_no_side_effects(self):
        for hosts in ([], (), None, 'codex', b'codex', ['unknown'], ['codex', None]):
            with self.subTest(hosts=hosts), self.assertRaises(ValueError):
                install(self.project, hosts)
        with self.assertRaises(ValueError):
            install(self.project, ['codex'], dry_run='yes')
        self.assertEqual(list(self.project.iterdir()), [])

    def test_missing_or_file_project_is_rejected_without_creation(self):
        missing = self.project / 'missing'
        with self.assertRaises(ValueError):
            install(missing, ['codex'])
        self.assertFalse(missing.exists())
        target = self.write('not-a-directory', 'existing file\n')
        with self.assertRaises(ValueError):
            install(target, ['codex'])
        self.assertEqual(target.read_text(), 'existing file\n')

    def test_install_preserves_settings_mcp_and_private_memory(self):
        unrelated = {'.no-mistakes/memory.json': '[{"text":"synthetic private preference"}]\n',
                     '.mcp.json': '{"mcpServers": {}}\n',
                     '.claude/settings.json': '{"permissions": {"defaultMode": "default"}}\n',
                     '.vscode/settings.json': '{"editor.tabSize": 4}\n',
                     '.codex/config.toml': 'approval_policy = "on-request"\n'}
        for relative, content in unrelated.items():
            self.write(relative, content)
        install(self.project, list(HOSTS))
        for relative, content in unrelated.items():
            self.assertEqual((self.project / relative).read_bytes(), content.encode())
        installed = set(self.snapshot()) - set(unrelated)
        expected = {f'{SKILL_PATH}/{name}' for name in skill_payload()}
        expected.update(set(HOSTS.values()))
        expected.update((MANIFEST_PATH, '.claude/commands/no-mistakes.md'))
        self.assertEqual(installed, expected)


class HostInstallCliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name)

    def test_repeatable_hosts_dry_run_and_install_json(self):
        arguments = ['install', '--host', 'codex', '--host', 'claude',
                     '--project', str(self.project)]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(arguments + ['--dry-run']), 0)
        preview = json.loads(output.getvalue())
        self.assertEqual(preview['hosts'], ['codex', 'claude'])
        self.assertTrue(preview['dry_run'])
        self.assertEqual(list(self.project.iterdir()), [])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(arguments), 0)
        result = json.loads(output.getvalue())
        self.assertFalse(result['dry_run'])
        self.assertTrue((self.project / 'AGENTS.md').is_file())
        self.assertTrue((self.project / 'CLAUDE.md').is_file())
        self.assertFalse((self.project / '.no-mistakes').exists())

    def test_unknown_or_missing_host_is_cli_input_error(self):
        for arguments in (['install', '--host', 'unknown'], ['install']):
            with self.subTest(arguments=arguments), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    main(arguments + ['--project', str(self.project)])
                self.assertEqual(error.exception.code, 2)
        self.assertEqual(list(self.project.iterdir()), [])

    def test_missing_project_returns_error_without_traceback(self):
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            status = main(['install', '--host', 'codex', '--project', str(self.project / 'missing')])
        self.assertEqual(status, 2)
        self.assertNotIn('Traceback', errors.getvalue())
        self.assertEqual(list(self.project.iterdir()), [])

    def test_ownership_conflict_returns_error_without_traceback(self):
        target = self.project / '.cursor/rules/no-mistakes.mdc'
        target.parent.mkdir(parents=True)
        target.write_text('Existing rule\n')
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            status = main(['install', '--host', 'cursor', '--project', str(self.project)])
        self.assertEqual(status, 2)
        self.assertNotIn('Traceback', errors.getvalue())
        self.assertEqual(target.read_text(), 'Existing rule\n')
        self.assertFalse((self.project / SKILL_PATH).exists())


if __name__ == '__main__':
    unittest.main()
