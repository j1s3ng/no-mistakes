import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class RetrievalCliTests(unittest.TestCase):
    def run_cli(self, *args, input=None):
        return subprocess.run([sys.executable, '-m', 'no_mistakes', 'retrieve', *args],
                              input=input, capture_output=True, text=True)

    def test_local_corpus_is_scoped_and_unverified(self):
        result = self.run_cli('--corpus', 'docs/corpus.example.json', '--query', 'retry',
                              '--scope', 'project:demo')
        self.assertEqual(result.returncode, 0, result.stderr)
        records = json.loads(result.stdout)
        self.assertFalse(records['verified'])
        self.assertTrue(records['evidence'])
        self.assertTrue(all(e['scope'] == 'project:demo' for e in records['evidence']))

    def test_query_stdin_and_empty_results(self):
        result = self.run_cli('--corpus', 'docs/corpus.example.json', '--scope', 'missing', input='retry')
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(json.loads(result.stdout)['evidence'], [])

    def test_query_file_and_limit(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'query.txt'
            path.write_text('checkout')
            result = self.run_cli('--corpus', 'docs/corpus.example.json', '--query-file', str(path),
                                  '--scope', 'project:demo', '--limit', '1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(json.loads(result.stdout)['evidence']), 1)

    def test_external_endpoint_without_reviewed_query_never_runs(self):
        result = self.run_cli('--endpoint', 'https://never-contact.example.invalid/search',
                              '--query', 'private input', '--scope', 'project:demo')
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('sanitization_required', result.stdout)
        self.assertNotIn('private input', result.stdout)

    def test_invalid_limit_fails(self):
        result = self.run_cli('--corpus', 'docs/corpus.example.json', '--query', 'retry',
                              '--scope', 'project:demo', '--limit', '0')
        self.assertEqual(result.returncode, 2)


if __name__ == '__main__':
    unittest.main()
