from typing import Optional
from app.core.config import settings
from app.services.sms.base import BaseSMSProvider, SMSProviderError
from app.services.sms.console import ConsoleSMSProvider
from app.services.sms.mock import MockSMSProvider
from app.services.sms.twilio import TwilioSMSProvider

# Global singleton mock provider for test inspections
mock_sms_provider = MockSMSProvider()


def get_sms_provider(provider_type: Optional[str] = None) -> BaseSMSProvider:
    """
    Factory resolving the active SMS provider according to settings.
    Fails safely with SMSProviderError if provider is unconfigured or unsupported.
    """
    provider = (provider_type or settings.SMS_PROVIDER).lower().strip()

    if provider == "mock":
        return mock_sms_provider
    elif provider == "console":
        return ConsoleSMSProvider()
    elif provider == "twilio":
        return TwilioSMSProvider()
    else:
        raise SMSProviderError(
            f"Unsupported or unconfigured SMS provider: '{provider}'. "
            "Please configure SMS_PROVIDER with a valid adapter (e.g. 'mock', 'console', 'twilio')."
        )


__all__ = [
    "BaseSMSProvider",
    "SMSProviderError",
    "MockSMSProvider",
    "ConsoleSMSProvider",
    "TwilioSMSProvider",
    "mock_sms_provider",
    "get_sms_provider",
]
