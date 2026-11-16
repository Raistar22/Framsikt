from __future__ import annotations

from typing import List, Dict, Any


class ChatMessage:
    """Represents a sent chat message."""

    def __init__(
        self,
        message: str,
        recipient_id: str,
        sender_id: str = "system",
        message_type: str = "direct",
    ) -> None:
        self.message = message
        self.recipient_id = recipient_id
        self.sender_id = sender_id
        self.message_type = message_type
        self.sent_at = None  # Will be set by the adapter


class ChatSimulator:
    """Simulated internal chat tool.

    Records messages that would be sent to the internal chat tool.
    Supports sending notifications to a volunteer or office channel
    and exposes sent messages for assertions in tests.
    """

    def __init__(self) -> None:
        self._messages: List[ChatMessage] = []

    def send_direct_message(self, employee_id: str, message: str) -> ChatMessage:
        """Send a direct message to an employee/volunteer."""
        msg = ChatMessage(
            message=message,
            recipient_id=employee_id,
            sender_id="system",
            message_type="direct",
        )
        self._messages.append(msg)
        return msg

    def send_office_message(self, office_id: str, message: str) -> ChatMessage:
        """Send a message to an office channel."""
        msg = ChatMessage(
            message=message,
            recipient_id=office_id,
            sender_id="system",
            message_type="office",
        )
        self._messages.append(msg)
        return msg

    def get_messages(self) -> List[ChatMessage]:
        """Get all sent messages for test assertions."""
        return list(self._messages)

    def clear(self) -> None:
        """Clear all recorded messages."""
        self._messages.clear()

    def find_messages(self, recipient_id: str | None = None, message_type: str | None = None) -> List[ChatMessage]:
        """Find messages by recipient or type."""
        results = self._messages
        if recipient_id:
            results = [m for m in results if m.recipient_id == recipient_id]
        if message_type:
            results = [m for m in results if m.message_type == message_type]
        return results

    def find_messages_containing(self, substring: str) -> List[ChatMessage]:
        """Find messages containing a substring."""
        return [m for m in self._messages if substring in m.message]