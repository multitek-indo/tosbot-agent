import os
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import httpx
from tosbot_ai.ai import AI
from tosbot_ai.config import Settings

ROOT = Path(__file__).resolve().parents[1]
MODEL = 'gemini-3.1-flash-lite'

class GeminiDefaultTests(unittest.TestCase):
    def test_defaults_consistent(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(Settings.load().gemini_model, MODEL)
        self.assertIn('GEMINI_MODEL=' + MODEL, (ROOT / '.env.example').read_text().splitlines())
        self.assertIn("'GEMINI_BASE_URL','" + MODEL + "'", (ROOT / 'scripts/doctor.py').read_text())

    def test_override_preserved(self):
        with patch.dict(os.environ, {'GEMINI_MODEL': 'custom-model'}, clear=True):
            self.assertEqual(Settings.load().gemini_model, 'custom-model')

    def test_fallback_uses_new_default(self):
        with patch.dict(os.environ, {'GROQ_API_KEY': 'test', 'GEMINI_API_KEY': 'test'}, clear=True):
            ai = AI(Settings.load())
        response = MagicMock()
        response.json.return_value = {'choices': [{'message': {'content': '{"action":"chat","data":{}}'}}]}
        client = MagicMock()
        client.__enter__.return_value = client
        client.post.side_effect = [httpx.ConnectError('simulated outage'), response]
        with patch('tosbot_ai.ai.httpx.Client', return_value=client):
            self.assertIn('chat', ai._complete([{'role': 'user', 'content': 'test'}], expect_action=True))
        calls = client.post.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].kwargs['json']['model'], 'openai/gpt-oss-120b')
        self.assertEqual(calls[1].kwargs['json']['model'], MODEL)
        self.assertIn('generativelanguage.googleapis.com', calls[1].args[0])
