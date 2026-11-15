"""LangGraph stateful turn router (MIT upstream: github.com/langchain-ai/langgraph).

The graph only interprets natural language. Tools, filesystem access, service
restart, document creation and finance writes remain in the deterministic Engine.
Its SQLite checkpoint is per Telegram owner, and conversation state survives
process restarts. The old TosBot database is not migrated or overwritten.
"""
from __future__ import annotations
import logging
import os
import re
import sqlite3
from pathlib import Path
from typing import TypedDict

log = logging.getLogger(__name__)

class TurnState(TypedDict, total=False):
    message: str
    draft: dict | None
    seed_history: list[dict]
    recent_turns: list[dict]
    parsed: dict
    response: str


def _safe_memory(text: str, limit: int = 3000) -> str:
    """Redact obvious credentials before writing either SQLite history."""
    value = str(text or '')[:limit]
    value = re.sub(r'(?i)(https?://api\.telegram\.org/bot)\d{7,12}:[A-Za-z0-9_-]{20,}', r'\1[TELEGRAM_TOKEN]', value)
    value = re.sub(r'(?<![A-Za-z0-9_])\d{7,12}:[A-Za-z0-9_-]{20,}', '[TELEGRAM_TOKEN]', value)
    value = re.sub(r'\b(?:sk|gsk|AIza)[A-Za-z0-9_\-]{15,}\b', '[SECRET]', value)
    value = re.sub(r'(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}', 'Bearer [SECRET]', value)
    value = re.sub(r'(?i)(?:token|api[_ -]?key|password|secret|private[_ -]?key)\s*[:=]\s*\S+', '[RAHASIA]', value)
    return value


def _safe_checkpoint_data(value, depth: int = 0):
    """Bound and redact data sent through the persisted LangGraph state."""
    if depth > 8:
        return '[TRUNCATED]'
    if isinstance(value, str):
        return _safe_memory(value, 4000)
    if isinstance(value, list):
        return [_safe_checkpoint_data(v, depth + 1) for v in value[:30]]
    if isinstance(value, dict):
        out = {}
        for k, v in list(value.items())[:60]:
            key = str(k)[:100]
            if re.search(r'(?i)(?:secret|token|password|api[_-]?key|private[_-]?key)', key):
                out[key] = '[RAHASIA]'
            else:
                out[key] = _safe_checkpoint_data(v, depth + 1)
        return out
    if value is None or isinstance(value, (int, float, bool)):
        return value
    return _safe_memory(str(value), 500)


class ConversationGraph:
    def __init__(self, ai, owner: int, checkpoint_path: Path):
        # Lazy import avoids impacting diagnostic commands when LangGraph absent.
        from langgraph.graph import StateGraph, START, END
        from langgraph.checkpoint.sqlite import SqliteSaver
        from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
        self.ai = ai
        self.owner = str(owner)
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        # Database created with service UMask 0077.
        self.connection = sqlite3.connect(str(checkpoint_path), check_same_thread=False)
        if checkpoint_path.is_file():
            try: os.chmod(checkpoint_path, 0o600)
            except OSError: pass
        serializer = JsonPlusSerializer(allowed_msgpack_modules=None)
        self.saver = SqliteSaver(self.connection, serde=serializer)
        builder = StateGraph(TurnState)
        builder.add_node('interpret_user', self._interpret)
        builder.add_edge(START, 'interpret_user')
        builder.add_edge('interpret_user', END)
        self.graph = builder.compile(checkpointer=self.saver)
        self.config = {'configurable': {'thread_id': self.owner}}

    def _interpret(self, state: TurnState) -> dict:
        history = (state.get('recent_turns') or state.get('seed_history') or [])[-30:]
        parsed = self.ai.understand(state['message'], history, state.get('draft'))
        return {'parsed': parsed}

    def interpret(self, message: str, draft: dict | None, seed_history: list[dict]) -> dict:
        values = self.graph.invoke({
            'message': _safe_memory(message),
            'draft': _safe_checkpoint_data(draft),
            'seed_history': _safe_checkpoint_data(seed_history[-20:]),
        }, self.config)
        return values['parsed']

    def recent(self) -> list[dict]:
        state = self.graph.get_state(self.config)
        if state and state.values:
            return (state.values.get('recent_turns') or [])[-30:]
        return []

    def remember(self, user: str, reply: str) -> None:
        history = self.recent()
        history.extend([
            {'role': 'user', 'content': _safe_memory(user)},
            {'role': 'assistant', 'content': _safe_memory(reply)},
        ])
        self.graph.update_state(self.config, {
            'recent_turns': history[-30:],
            # Checkpoint only the latest turn, not outdated open drafts.
            'draft': None, 'seed_history': [],
        })

    def close(self) -> None:
        self.connection.close()
