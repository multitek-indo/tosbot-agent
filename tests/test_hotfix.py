import unittest
from dataclasses import replace
from unittest.mock import patch
from tosbot_ai.ai import AI
from tosbot_ai.config import Settings

class HotfixTests(unittest.TestCase):
    def test_groq_mandatory(self):
        with patch.dict('os.environ', {'GROQ_API_KEY':'', 'GEMINI_API_KEY':'gemini-test',
                                     'TELEGRAM_BOT_TOKEN':'bot-token', 'AI_PRIMARY':'groq'}):
            s=Settings.load()
        with self.assertRaisesRegex(ValueError, 'GROQ_API_KEY'):
            s.validate()
        none_config=replace(s,gemini_key='')
        with self.assertRaisesRegex(RuntimeError, 'GROQ_API_KEY'):
            AI(none_config)._complete([{'role':'user','content':'halo'}])

    def test_groq_before_gemini(self):
        with patch.dict('os.environ',{'GROQ_API_KEY':'groq-test','GEMINI_API_KEY':'gemini-test',
                                     'TELEGRAM_BOT_TOKEN':'bot-token', 'AI_PRIMARY':'groq'}):
            s=Settings.load()
        s.validate()
        self.assertEqual([x[0] for x in AI(s)._providers()], ['groq','gemini'])

if __name__ == '__main__': unittest.main()

class RedactionAuditTests(unittest.TestCase):
    def test_redact_memory_and_checkpoint_packet(self):
        from tosbot_ai.conversation import _safe_memory, _safe_checkpoint_data
        src='password=SUPERSECRET123 and bot ' + '1234567890:' + 'ABCDEFabcdefghijklmnopqrstuv12345'
        self.assertNotIn('SUPERSECRET123',_safe_memory(src))
        self.assertNotIn('ABCDEFabc',_safe_memory(src))
        url='https://api.telegram.org/bot' + '1234567890:' + 'ABCDEFabcdefghijklmnopqrstuv12345' + '/getUpdates'
        self.assertNotIn('ABCDEFabc',_safe_memory(url))
        data=_safe_checkpoint_data({'GROQ_API_KEY':'gsk_12345678901234567890123', 'note':'password=HELLO_PRIVATE'})
        self.assertEqual(data['GROQ_API_KEY'],'[RAHASIA]')
        self.assertNotIn('HELLO_PRIVATE',data['note'])
