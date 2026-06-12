from pydantic import BaseModel
from typing import Optional

class WhatsAppEntrada(BaseModel):
    From: str
    To: str
    Body: str
    ProfileName: Optional[str] = ""