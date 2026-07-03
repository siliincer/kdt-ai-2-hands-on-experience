from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserReadSchema(BaseModel):
    id: str
    email: EmailStr
    name: str | None = None

    model_config = ConfigDict(from_attributes=True)


class UserSignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str | None = None


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str
