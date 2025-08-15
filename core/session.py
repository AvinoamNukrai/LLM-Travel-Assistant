"""
core/session.py

Conversation session state and lightweight slot memory.
- Slots: structured fields the assistant remembers (city, dates, etc.)
- Session: conversation history plus slots; utility helpers
"""

from dataclasses import dataclass, field


@dataclass
class Slots:
    city = None
    country = None
    start_date = None  # ISO YYYY-MM-DD
    end_date = None    # ISO YYYY-MM-DD
    month = None
    interests = None
    budget_hint = None
    kid_friendly = None
    lat = None
    lon = None
    last_intent = None


@dataclass
class Session:
    history = field(default_factory=list)  # list of {role, content}
    slots = field(default_factory=Slots)

    def add(self, role, content):
        """Append a message to the conversation history."""
        self.history.append({"role": role, "content": content})

    def recent_history(self, limit):
        """Return the last N messages from the history."""
        return self.history[-limit:]
