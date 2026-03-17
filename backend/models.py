from pydantic import BaseModel, Field, validator
import re
from typing import Optional

class UserCreate(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=100)
    reg_no: str
    password: str = Field(..., min_length=8)

    @validator('reg_no')
    def validate_reg_no(cls, v):
        pattern = r'^[A-Z]{3}\/[A-Z]{3}\/\d{2}\/\d{4}$'
        if not re.match(pattern, v):
            raise ValueError('REG NO must be in format: XXX/XXX/XX/XXXX (all caps)')
        return v

class UserLogin(BaseModel):
    reg_no: str
    password: str

    @validator('reg_no')
    def validate_reg_no(cls, v):
        pattern = r'^[A-Z]{3}\/[A-Z]{3}\/\d{2}\/\d{4}$'
        if not re.match(pattern, v):
            raise ValueError('REG NO must be in format: XXX/XXX/XX/XXXX (all caps)')
        return v

class UserResponse(BaseModel):
    id: str
    full_name: str
    reg_no: str
    created_at: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse
