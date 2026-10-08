import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from no_mistakes.cli import _tool_document


class ToolDocumentReadTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.document = self.root / "plan.json"

    def test_regular_document_is_read_without_changes(self):
        content = '{"nested": {"value": "caf\u00e9"}, "items": [1, 2]}'
        self.document.write_text(content, encoding="utf-8")
        before = self.document.stat()
        self.assertEqual(_tool_document(self.document), json.loads(content))
        self.assertEqual(self.document.read_text(encoding="utf-8"), content)
        self.assertEqual(self.document.stat().st_mtime_ns, before.st_mtime_ns)
        self.assertEqual(list(self.root.iterdir()), [self.document])

    def test_size_boundary_accepts_limit_and_rejects_one_byte_more(self):
        prefix, suffix = b'{"padding":"', b'"}'
        exact = prefix + b"x" * (262_144 - len(prefix) - len(suffix)) + suffix
        self.document.write_bytes(exact)
        self.assertEqual(len(_tool_document(self.document)["padding"]),
                         262_144 - len(prefix) - len(suffix))
        self.document.write_bytes(exact + b" ")
        with self.assertRaisesRegex(ValueError, "exceeds 256 KiB"):
            _tool_document(self.document)

    def test_duplicate_keys_are_rejected_at_any_depth(self):
        for content in ('{"value": 1, "value": 2}',
                        '{"nested": {"value": 1, "value": 2}}'):
            with self.subTest(content=content):
                self.document.write_text(content, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "duplicate keys"):
                    _tool_document(self.document)

    def test_missing_and_directory_paths_fail_without_echoing_values(self):
        private_path = self.root / "SYNTHETIC_PRIVATE_PATH"
        for candidate in (private_path, self.root):
            with self.subTest(kind="directory" if candidate.is_dir() else "missing"):
                with self.assertRaisesRegex(ValueError, "regular file") as error:
                    _tool_document(candidate)
                self.assertNotIn("SYNTHETIC_PRIVATE_PATH", str(error.exception))
                self.assertNotIn(str(self.root), str(error.exception))

    @unittest.skipUnless(hasattr(os, "symlink"), "Symlinks unavailable")
    def test_selected_symlink_is_rejected_without_reading_its_target(self):
        target = self.root / "target.json"
        target.write_text('{"secret": "SYNTHETIC_PRIVATE_VALUE"}', encoding="utf-8")
        try:
            self.document.symlink_to(target)
        except (NotImplementedError, OSError):
            self.skipTest("Symlink creation unavailable")
        with patch("no_mistakes.cli.os.open") as opening:
            with self.assertRaisesRegex(ValueError, "without symlinks") as error:
                _tool_document(self.document)
        self.assertNotIn("SYNTHETIC_PRIVATE_VALUE", str(error.exception))
        opening.assert_not_called()

    @unittest.skipUnless(os.name == "posix" and hasattr(os, "mkfifo"), "POSIX FIFO required")
    def test_static_fifo_is_rejected_without_blocking(self):
        os.mkfifo(self.document)
        program = textwrap.dedent("""\
            from pathlib import Path
            import sys
            from no_mistakes.cli import _tool_document
            try:
                _tool_document(Path(sys.argv[1]))
            except ValueError as error:
                print(str(error))
            else:
                raise SystemExit('Unexpected accepted FIFO')
            """)
        result = subprocess.run([sys.executable, "-c", program, str(self.document)],
                                stdin=subprocess.DEVNULL, capture_output=True,
                                text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("regular file", result.stdout)
        self.assertEqual(result.stderr, "")

    @unittest.skipUnless(os.name == "posix" and hasattr(os, "mkfifo"), "POSIX FIFO required")
    def test_regular_file_replaced_by_fifo_during_open_is_rejected_without_blocking(self):
        self.document.write_text('{}', encoding="utf-8")
        program = textwrap.dedent("""\
            import os
            from pathlib import Path
            import sys
            from unittest.mock import patch
            from no_mistakes.cli import _tool_document
            original_open = os.open
            def replace_with_fifo(path, flags):
                Path(path).unlink()
                os.mkfifo(path)
                return original_open(path, flags)
            with patch('no_mistakes.cli.os.open', side_effect=replace_with_fifo):
                try:
                    _tool_document(Path(sys.argv[1]))
                except ValueError as error:
                    print(str(error))
                else:
                    raise SystemExit('Unexpected accepted replacement FIFO')
            """)
        result = subprocess.run([sys.executable, "-c", program, str(self.document)],
                                stdin=subprocess.DEVNULL, capture_output=True,
                                text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("changed while opening", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_opened_different_regular_file_is_rejected_and_descriptor_closed(self):
        self.document.write_text('{}', encoding="utf-8")
        replacement = self.root / "replacement.json"
        replacement.write_text('{"secret":"SYNTHETIC_PRIVATE_VALUE"}', encoding="utf-8")
        descriptor = os.open(replacement, os.O_RDONLY)
        with patch("no_mistakes.cli.os.open", return_value=descriptor):
            with self.assertRaisesRegex(ValueError, "changed while opening") as error:
                _tool_document(self.document)
        self.assertNotIn("SYNTHETIC_PRIVATE_VALUE", str(error.exception))
        with self.assertRaises(OSError):
            os.fstat(descriptor)


if __name__ == "__main__":
    unittest.main()
