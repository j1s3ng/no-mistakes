import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from no_mistakes.diagnostics import NOTICE, doctor
from no_mistakes.hosts import (
    BEGIN, END, HOSTS, MANIFEST_PATH, SKILL_PATH, install, skill_payload,
)


class InstallationDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = (Path(self.temporary.name) / "project").resolve()
        self.project.mkdir()

    def write(self, relative, content):
        target = self.project / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
        return target

    def snapshot(self):
        return {str(path.relative_to(self.project)): path.read_bytes() if path.is_file() else None
                for path in self.project.rglob("*")}

    def findings(self, result):
        return {(issue["code"], issue["path"]) for issue in result["issues"]}

    def test_current_install_for_all_profiles_is_healthy_and_read_only(self):
        install(self.project, list(HOSTS))
        before = self.snapshot()
        result = doctor(self.project, list(HOSTS))
        self.assertTrue(result["ok"])
        self.assertEqual(result["issues"], [])
        self.assertEqual(result["hosts"], list(HOSTS))
        self.assertEqual(result["project"], str(self.project))
        self.assertEqual(result["notice"], NOTICE)
        self.assertEqual(self.snapshot(), before)

    def test_empty_project_reports_missing_installation_without_creating_directories(self):
        result = doctor(self.project, ["codex"])
        findings = self.findings(result)
        self.assertFalse(result["ok"])
        self.assertIn(("missing_manifest", MANIFEST_PATH), findings)
        self.assertIn(("missing_file", f"{SKILL_PATH}/SKILL.md"), findings)
        self.assertIn(("missing_route", "AGENTS.md"), findings)
        self.assertEqual(list(self.project.iterdir()), [])
        for issue in result["issues"]:
            self.assertEqual(set(issue), {"code", "path", "message", "action"})
            self.assertTrue(issue["message"])
            self.assertTrue(issue["action"])

    def test_missing_reference_and_route_are_reported_together_without_changes(self):
        install(self.project, ["codex"])
        reference = f"{SKILL_PATH}/references/web-research.md"
        (self.project / reference).unlink()
        (self.project / "AGENTS.md").unlink()
        before = self.snapshot()
        result = doctor(self.project, ["codex"])
        self.assertEqual(self.findings(result), {
            ("missing_file", reference), ("missing_route", "AGENTS.md"),
        })
        self.assertEqual(self.snapshot(), before)

    def test_matching_ownership_hash_with_old_payload_is_outdated(self):
        previous = dict(skill_payload())
        previous["SKILL.md"] = b"# Previous packaged skill\n"
        with patch("no_mistakes.hosts.skill_payload", return_value=previous):
            install(self.project, ["codex"])
        result = doctor(self.project, ["codex"])
        self.assertEqual(self.findings(result), {("outdated_file", f"{SKILL_PATH}/SKILL.md")})

    def test_locally_modified_payload_is_reported_without_printing_contents(self):
        install(self.project, ["codex"])
        target = f"{SKILL_PATH}/SKILL.md"
        self.write(target, "private-local-content\n")
        result = doctor(self.project, ["codex"])
        self.assertEqual(self.findings(result), {("modified_file", target)})
        self.assertNotIn("private-local-content", json.dumps(result))

    def test_identical_payload_without_ownership_record_is_unowned(self):
        install(self.project, ["codex"])
        manifest_path = self.project / MANIFEST_PATH
        manifest = json.loads(manifest_path.read_text())
        target = f"{SKILL_PATH}/SKILL.md"
        del manifest["files"][target]
        manifest_path.write_text(json.dumps(manifest))
        self.assertEqual(self.findings(doctor(self.project, ["codex"])), {("unowned_file", target)})

    def test_invalid_manifests_do_not_prevent_independent_route_checks(self):
        install(self.project, ["codex"])
        (self.project / "AGENTS.md").unlink()
        invalid = [b"not json", b"\xff", b"[" * 2000 + b"0" + b"]" * 2000,
                   b"[]", b"{}", b'{"version": true, "files": {}}',
                   b'{"version": 2, "files": {}}', b'{"version": 1, "files": []}',
                   {"version": 1, "files": {"AGENTS.md": "0" * 64}},
                   {"version": 1, "files": {MANIFEST_PATH: "0" * 64}},
                   {"version": 1, "files": {f"{SKILL_PATH}//SKILL.md": "0" * 64}},
                   {"version": 1, "files": {f"{SKILL_PATH}/../outside.md": "0" * 64}},
                   {"version": 1, "files": {f"{SKILL_PATH}/\x00.md": "0" * 64}},
                   {"version": 1, "files": {f"{SKILL_PATH}/\ud800.md": "0" * 64}},
                   {"version": 1, "files": {f"{SKILL_PATH}/SKILL.md": "bad-hash"}}]
        for record in invalid:
            with self.subTest(record=record):
                self.write(MANIFEST_PATH, json.dumps(record) if isinstance(record, dict) else record)
                result = doctor(self.project, ["codex"])
                findings = self.findings(result)
                self.assertIn(("invalid_manifest", MANIFEST_PATH), findings)
                self.assertIn(("missing_route", "AGENTS.md"), findings)
                self.assertFalse(result["ok"])
                before = self.snapshot()
                with self.assertRaises(ValueError):
                    install(self.project, ["codex"])
                self.assertEqual(self.snapshot(), before)

    def test_missing_manifest_reports_unowned_existing_payload(self):
        install(self.project, ["codex"])
        (self.project / MANIFEST_PATH).unlink()
        findings = self.findings(doctor(self.project, ["codex"]))
        self.assertIn(("missing_manifest", MANIFEST_PATH), findings)
        self.assertIn(("unowned_file", f"{SKILL_PATH}/SKILL.md"), findings)

    def test_selected_claude_command_and_cursor_rule_are_checked(self):
        install(self.project, ["claude", "cursor"])
        command = ".claude/commands/no-mistakes.md"
        (self.project / command).unlink()
        self.write(HOSTS["cursor"], "locally customized rule\n")
        self.assertEqual(self.findings(doctor(self.project, ["claude", "cursor"])), {
            ("missing_file", command), ("modified_file", HOSTS["cursor"]),
        })

    def test_owned_old_native_adapters_are_outdated(self):
        with patch("no_mistakes.hosts.CLAUDE_COMMAND", "# Previous command\n"), \
                patch("no_mistakes.hosts.CURSOR_RULE", "# Previous rule\n"):
            install(self.project, ["claude", "cursor"])
        self.assertEqual(self.findings(doctor(self.project, ["claude", "cursor"])), {
            ("outdated_file", ".claude/commands/no-mistakes.md"),
            ("outdated_file", HOSTS["cursor"]),
        })

    def test_hosts_are_deduplicated_and_shared_routing_is_checked_once(self):
        install(self.project, ["codex"])
        (self.project / "AGENTS.md").unlink()
        result = doctor(self.project, ["codex", "generic", "codex"])
        self.assertEqual(result["hosts"], ["codex", "generic"])
        self.assertEqual(len(result["issues"]), 1)
        self.assertEqual(self.findings(result), {("missing_route", "AGENTS.md")})

    def test_missing_invalid_and_outdated_routes_preserve_project_text(self):
        install(self.project, ["codex"])
        cases = [
            (b"# Existing project conventions\n", "missing_route"),
            (BEGIN.encode() + b"\nmissing end", "invalid_route"),
            (b"\xff", "invalid_route"),
            ((BEGIN + "\nprevious routing\n" + END + "\n").encode(), "outdated_route"),
        ]
        for content, expected in cases:
            with self.subTest(expected=expected, content=content):
                path = self.write("AGENTS.md", content)
                self.assertEqual(self.findings(doctor(self.project, ["codex"])), {(expected, "AGENTS.md")})
                self.assertEqual(path.read_bytes(), content)

    def test_custom_text_outside_current_crlf_routing_is_healthy(self):
        self.write("AGENTS.md", "# Existing café\r\n")
        install(self.project, ["codex"])
        path = self.project / "AGENTS.md"
        path.write_bytes(path.read_bytes() + b"\r\n# More project conventions\r\n")
        before = self.snapshot()
        self.assertTrue(doctor(self.project, ["codex"])["ok"])
        self.assertEqual(self.snapshot(), before)

    def test_symlink_files_and_parents_are_not_read_or_followed(self):
        outside = Path(self.temporary.name) / "outside"
        outside.mkdir()
        secret = outside / "secret.md"
        secret.write_text("outside-private-content\n")
        (self.project / "AGENTS.md").symlink_to(secret)
        (self.project / ".agents").symlink_to(outside, target_is_directory=True)
        original_open = io.open
        forbidden_opens = []

        def guarded_open(file, *args, **kwargs):
            path = Path(file)
            if path == secret or path == self.project / "AGENTS.md" or self.project / ".agents" in path.parents:
                forbidden_opens.append(path)
            return original_open(file, *args, **kwargs)

        with patch("io.open", guarded_open), patch("builtins.open", guarded_open):
            result = doctor(self.project, ["codex"])
        self.assertEqual(forbidden_opens, [])
        self.assertIn(("unsafe_path", MANIFEST_PATH), self.findings(result))
        self.assertIn(("unsafe_path", "AGENTS.md"), self.findings(result))
        self.assertNotIn("outside-private-content", json.dumps(result))
        self.assertEqual(secret.read_text(), "outside-private-content\n")
        self.assertEqual(list(outside.iterdir()), [secret])

    def test_unreadable_file_does_not_leak_exception_text_or_block_other_checks(self):
        install(self.project, ["codex"])
        missing = f"{SKILL_PATH}/references/web-research.md"
        (self.project / missing).unlink()
        original_read = Path.read_bytes

        def guarded_read(path):
            if path == self.project / "AGENTS.md":
                raise PermissionError("private-exception-detail")
            return original_read(path)

        with patch.object(Path, "read_bytes", guarded_read):
            result = doctor(self.project, ["codex"])
        self.assertEqual(self.findings(result), {
            ("missing_file", missing), ("unreadable_file", "AGENTS.md"),
        })
        self.assertNotIn("private-exception-detail", json.dumps(result))

    def test_retired_owned_files_and_missing_records_are_reported_without_removal(self):
        previous = dict(skill_payload())
        retired = {
            "references/retired-clean.md": b"# Old packaged reference\n",
            "references/retired-modified.md": b"# Old packaged reference\n",
            "references/retired-missing.md": b"# Old packaged reference\n",
        }
        previous.update(retired)
        with patch("no_mistakes.hosts.skill_payload", return_value=previous):
            install(self.project, ["codex"])
        self.write(f"{SKILL_PATH}/references/retired-modified.md", "# Local edits\n")
        (self.project / SKILL_PATH / "references/retired-missing.md").unlink()
        before = self.snapshot()
        self.assertEqual(self.findings(doctor(self.project, ["codex"])), {
            ("retired_file", f"{SKILL_PATH}/references/retired-clean.md"),
            ("modified_file", f"{SKILL_PATH}/references/retired-modified.md"),
            ("retired_record", f"{SKILL_PATH}/references/retired-missing.md"),
        })
        self.assertEqual(self.snapshot(), before)

    def test_unselected_adapters_extras_and_private_context_are_never_read(self):
        install(self.project, ["codex", "claude", "cursor"])
        private = [".claude/commands/no-mistakes.md", HOSTS["cursor"],
                   f"{SKILL_PATH}/references/local-guide.md", ".no-mistakes/memory.json", ".mcp.json"]
        for relative in private:
            self.write(relative, "private-unrelated-content\n")
        original_open = io.open
        forbidden_opens = []
        blocked = {self.project / relative for relative in private}

        def guarded_open(file, *args, **kwargs):
            if Path(file) in blocked:
                forbidden_opens.append(Path(file))
            return original_open(file, *args, **kwargs)

        before = self.snapshot()
        with patch("io.open", guarded_open), patch("builtins.open", guarded_open):
            result = doctor(self.project, ["codex"])
        self.assertEqual(forbidden_opens, [])
        self.assertTrue(result["ok"])
        self.assertEqual(self.snapshot(), before)

    def test_invalid_inputs_are_rejected_without_side_effects(self):
        for hosts in ([], (), None, "codex", b"codex", ["unknown"], ["codex", None]):
            with self.subTest(hosts=hosts), self.assertRaises(ValueError):
                doctor(self.project, hosts)
        for project in (self.project / "missing", None, 1, b"not-a-path"):
            with self.subTest(project=project), self.assertRaises(ValueError):
                doctor(project, ["codex"])
        target = self.write("not-a-directory", "existing file\n")
        with self.assertRaises(ValueError):
            doctor(target, ["codex"])
        self.assertEqual(self.snapshot(), {"not-a-directory": b"existing file\n"})


if __name__ == "__main__":
    unittest.main()
