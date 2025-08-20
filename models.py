from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional

class Cliente(BaseModel):
    id: Optional[int] = None
    nome: str
    telefone: Optional[str] = None
    email: Optional[EmailStr] = None

    @field_validator("telefone")
    @classmethod
    def normaliza_tel(cls, v: Optional[str]):
        if not v:
            return v
        return "".join([c for c in v if c.isdigit() or c == "+"])
