"""
assistant/session.py

Conversation session state and lightweight slot memory.

Classes:
- Slots: structured memory for the conversation (destination, dates/month, preferences, geo coords, last intent).
- Session: message history plus slots, with small helpers to append and slice recent history.
"""

from dataclasses import dataclass, field


@dataclass
class Slots:
    city: str | None = None
    country: str | None = None
    start_date: str | None = None  # ISO YYYY-MM-DD
    end_date: str | None = None    # ISO YYYY-MM-DD
    month: str | None = None
    interests: str | None = None
    budget_hint: str | None = None
    kid_friendly: bool | None = None
    lat: float | None = None
    lon: float | None = None
    last_intent: str | None = None


@dataclass
class Session:
    history: list[dict[str, str]] = field(default_factory=list)  # list of {role, content}
    slots: Slots = field(default_factory=Slots)

    def add(self, role, content):
        """Append a message to the conversation history."""
        self.history.append({"role": role, "content": content})

    def recent_history(self, limit):
        """Return the last N messages from the history."""
        return self.history[-limit:]


