from abc import ABC, abstractmethod


class SMSProviderError(Exception):
    """Raised when SMS delivery fails or provider is improperly configured."""

    pass


class BaseSMSProvider(ABC):
    """
    Abstract interface for SMS delivery providers.
    All SMS integrations (Twilio, AWS SNS, Fast2SMS, etc.) must implement this interface.
    """

    @abstractmethod
    def send_otp(self, phone_number: str, otp: str) -> bool:
        """
        Deliver a one-time password to the target phone number.
        Returns True on success, or raises SMSProviderError on failure.
        """
        pass
