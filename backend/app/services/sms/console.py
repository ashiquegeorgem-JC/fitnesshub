from app.core.logging import logger
from app.services.sms.base import BaseSMSProvider


class ConsoleSMSProvider(BaseSMSProvider):
    """
    Development provider that outputs dispatch events to application logs.
    Strictly adheres to security policies: NEVER logs the plaintext OTP.
    """

    def send_otp(self, phone_number: str, otp: str) -> bool:
        masked = phone_number[:4] + "****" if len(phone_number) >= 4 else "****"
        logger.info(f"[SMS Provider - Console] One-time password dispatched to {masked}")
        return True
