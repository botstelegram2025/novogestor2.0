# config.py
import os
from dataclasses import dataclass

@dataclass(frozen=True)
class Config:
    # Telegram / DB
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")

    # WhatsApp (se você usa)
    WHATSAPP_API_URL: str = os.getenv("WHATSAPP_API_URL", "")

    # Mercado Pago
    MERCADO_PAGO_ACCESS_TOKEN: str = (
        os.getenv("MERCADO_PAGO_ACCESS_TOKEN")
        or os.getenv("MP_ACCESS_TOKEN", "")
    )
    MERCADO_PAGO_PUBLIC_KEY: str = (
        os.getenv("MERCADO_PAGO_PUBLIC_KEY")
        or os.getenv("MP_PUBLIC_KEY", "")
    )

    @staticmethod
    def assert_required() -> None:
        missing = []
        if not Config.BOT_TOKEN: missing.append("BOT_TOKEN")
        if not Config.MERCADO_PAGO_ACCESS_TOKEN: missing.append("MERCADO_PAGO_ACCESS_TOKEN (ou MP_ACCESS_TOKEN)")
        if missing:
            raise RuntimeError("Variáveis obrigatórias ausentes: " + ", ".join(missing))
