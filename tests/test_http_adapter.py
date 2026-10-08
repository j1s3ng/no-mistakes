import io
import json
import os
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from no_mistakes.http_adapter import JsonHttpRetriever, _NoRedirect
from no_mistakes.integrations import RetrievalRequest, retrieve


class HttpAdapterTests(unittest.TestCase):
    def request(self):
        return RetrievalRequest('private input', 'project:demo', 2)

    def test_https_explicit_and_no_credentials_in_url(self):
        for endpoint in ('http://example.invalid/search', 'https://user:pass@example.invalid',
                         'https://example.invalid/?token=secret', 'https://example.invalid/#secret'):
            with self.assertRaises(ValueError):
                JsonHttpRetriever('rag', endpoint)
        JsonHttpRetriever('rag', 'http://127.0.0.1:9000/search', allow_local_http=True)
        with self.assertRaises(ValueError):
            JsonHttpRetriever('rag', 'http://example.invalid', allow_local_http=True)

    def test_malformed_url_error_does_not_echo_credentials(self):
        with self.assertRaises(ValueError) as error:
            JsonHttpRetriever('rag', 'https://user:secret@exam／ple.com')
        self.assertNotIn('secret', str(error.exception))

    def test_no_redirect(self):
        self.assertIsNone(_NoRedirect().redirect_request(None, None, 302, '', {},
                                                        'https://other.invalid/'))

    @patch('no_mistakes.http_adapter.build_opener')
    def test_post_uses_sanitized_query_and_env_token(self, build):
        payload = {'evidence': [{'id': 'doc:1', 'text': 'Technical excerpt',
                               'source': 'https://docs.example.invalid/retry', 'scope': 'project:demo'}]}
        response = io.BytesIO(json.dumps(payload).encode())
        build.return_value.open.return_value = response
        adapter = JsonHttpRetriever('rag', 'https://rag.example.invalid/search', token_env='DEMO_RAG_TOKEN')
        with patch.dict(os.environ, {'DEMO_RAG_TOKEN': 'synthetic-secret'}):
            result = retrieve(self.request(), [adapter], sanitize_query=lambda q: 'retry timeout')
        sent = build.return_value.open.call_args.args[0]
        self.assertEqual(sent.get_method(), 'POST')
        self.assertEqual(json.loads(sent.data), {'query': 'retry timeout', 'scope': 'project:demo', 'limit': 2})
        self.assertEqual(sent.get_header('Authorization'), 'Bearer synthetic-secret')
        self.assertEqual(result['evidence'][0]['id'], 'doc:1')
        self.assertNotIn('synthetic-secret', json.dumps(result))

    @patch('no_mistakes.http_adapter.build_opener')
    def test_no_network_without_sanitizer(self, build):
        result = retrieve(self.request(), [JsonHttpRetriever('rag', 'https://rag.example.invalid')])
        build.assert_not_called()
        self.assertTrue(result['gaps'])

    @patch('no_mistakes.http_adapter.build_opener')
    def test_response_limit(self, build):
        build.return_value.open.return_value = io.BytesIO(b'x' * 11)
        adapter = JsonHttpRetriever('rag', 'https://rag.example.invalid', max_response_bytes=10)
        result = retrieve(self.request(), [adapter], sanitize_query=lambda q: 'safe')
        self.assertEqual(result['evidence'], [])
        self.assertTrue(result['gaps'])

    @patch('no_mistakes.http_adapter.build_opener')
    def test_transport_error_does_not_expose_private_details(self, build):
        build.return_value.open.side_effect = HTTPError('https://private.invalid/customer', 403,
                                                       'secret customer details', {}, None)
        result = retrieve(self.request(), [JsonHttpRetriever('rag', 'https://rag.example.invalid')],
                          sanitize_query=lambda q: 'safe')
        serialized = json.dumps(result)
        self.assertNotIn('private.invalid', serialized)
        self.assertNotIn('secret customer details', serialized)
        self.assertTrue(result['gaps'])


if __name__ == '__main__':
    unittest.main()
