from typing import Optional

from pydantic import BaseModel, Field


class CloudPermanentRequest(BaseModel):
    token: str = Field(min_length=40, max_length=4096)
    public_url: str = Field(min_length=9, max_length=240)
    autostart: bool = True


class CloudAutostartRequest(BaseModel):
    autostart: bool = True


class CloudQrRequest(BaseModel):
    url: Optional[str] = Field(default=None, max_length=240)
