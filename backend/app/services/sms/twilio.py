from typing import Optional
import httpx

from app.core.config import settings
from app.core.logging import logger
from app.services.sms.base import BaseSMSProvider, SMSProviderError


class TwilioSMSProvider(BaseSMSProvider):
    """
    Twilio SMS integration provider using Twilio Messages REST API.
    Fails safely if credentials are not configured.
    """

    def __init__(
        self,
        account_sid: Optional[str] = None,
        auth_token: Optional[str] = None,
        from_number: Optional[str] = None,
    ) -> None:
        self.account_sid = account_sid or settings.TWILIO_ACCOUNT_SID
        self.auth_token = auth_token or settings.TWILIO_AUTH_TOKEN
        self.from_number = from_number or settings.TWILIO_FROM_NUMBER

        if not (self.account_sid and self.auth_token and self.from_number):
            raise SMSProviderError(
                "Twilio SMS Provider is not fully configured. "
                "TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_FROM_NUMBER are required."
            )

    def send_otp(self, phone_number: str, otp: str) -> bool:
        url = (
            f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
        )
        body = f"Your Regal Fitness verification code is: {otp}. Valid for 10 minutes."

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    url,
                    data={
                        "From": self.from_number,
                        "To": phone_number,
                        "Body": body,
                    },
                    auth=(self.account_sid, self.auth_token),
                )
                if response.status_code not in (200, 201):
                    logger.error(
                        f"Twilio API error: status {response.status_code}, response: {response.text}"
                    )
                    raise SMSProviderError(
                        f"Twilio SMS delivery failed with status {response.status_code}."
                    )
                return True
        except httpx.RequestError as exc:
            logger.error(f"Network error communicating with Twilio: {str(exc)}")
            raise SMSProviderError(f"SMS service network error: {str(exc)}")
