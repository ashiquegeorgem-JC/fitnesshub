from typing import Dict, List
from app.services.sms.base import BaseSMSProvider


class MockSMSProvider(BaseSMSProvider):
    """
    In-memory mock provider for testing and offline verification.
    Records dispatched OTPs so tests can verify dispatch without external calls.
    """

    def __init__(self) -> None:
        self.sent_messages: List[Dict[str, str]] = []

    def send_otp(self, phone_number: str, otp: str) -> bool:
        self.sent_messages.append({
            "phone_number": phone_number,
            "otp": otp,
        })
        return True

    def clear(self) -> None:
        self.sent_messages.clear()

    def get_last_otp(self, phone_number: str) -> str:
        for msg in reversed(self.sent_messages):
            if msg["phone_number"] == phone_number:
                return msg["otp"]
        return ""
