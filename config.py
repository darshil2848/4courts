import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Flask
    SECRET_KEY: str = os.environ["SECRET_KEY"]
    DEBUG: bool = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    # WhatsApp Cloud API
    WA_API_VERSION: str = os.getenv("WHATSAPP_API_VERSION", "v19.0")
    WA_PHONE_NUMBER_ID: str = os.environ["WHATSAPP_PHONE_NUMBER_ID"]
    WA_ACCESS_TOKEN: str = os.environ["WHATSAPP_ACCESS_TOKEN"]
    WA_WEBHOOK_VERIFY_TOKEN: str = os.environ["WHATSAPP_WEBHOOK_VERIFY_TOKEN"]
    WA_APP_SECRET: str = os.environ["WHATSAPP_APP_SECRET"]

    # Playo Court Booking API
    PLAYO_AUTH_TOKEN: str = os.environ["PLAYO_AUTH_TOKEN"]

    # Derived base URL – never hardcode version strings elsewhere
    @property
    def WA_BASE_URL(self) -> str:  # noqa: N802
        return (
            f"https://graph.facebook.com/{self.WA_API_VERSION}"
            f"/{self.WA_PHONE_NUMBER_ID}/messages"
        )
