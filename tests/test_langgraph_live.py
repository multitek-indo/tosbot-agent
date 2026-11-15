"""Runs on VPS after pip installs LangGraph, skipped in offline build environment."""
import tempfile
import unittest
from pathlib import Path
from tosbot_ai.conversation import ConversationGraph

class GraphPersistenceIntegration(unittest.TestCase):
    def test_langgraph_checkpoint_survives_restart(self):
        try:
            import langgraph  # noqa: F401
        except ImportError:
            self.skipTest('LangGraph not downloaded in offline build environment')

        class MockAI:
            def understand(self, text, history, draft):
                return {'action':'chat', 'data':{}, 'history_len':len(history), 'draft_seen':draft}

        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'state.sqlite3'
            flow=ConversationGraph(MockAI(), 123, path)
            r=flow.interpret('halo', None, [])
            self.assertEqual(r['history_len'],0)
            flow.remember('halo','sugeng enjing')
            flow.close()
            resumed=ConversationGraph(MockAI(), 123, path)
            self.assertEqual(len(resumed.recent()),2)
            response=resumed.interpret('nderek takon',None,[])
            self.assertEqual(response['history_len'],2)
            resumed.close()

if __name__=='__main__':unittest.main()
