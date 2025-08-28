# config.py
import os
from dataclasses import dataclass

@dataclass
class Config:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    # adicione outros que você usa:
    # ADMIN_CHAT_ID: str = os.getenv("ADMIN_CHAT_ID", "")
    # ... 

    @classmethod
    def validate(cls) -> "Config":
        cfg = cls()
        if not cfg.BOT_TOKEN:
            raise RuntimeError("BOT_TOKEN não configurado (env)")
        return cfg
