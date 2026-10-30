from pydantic import BaseModel, ConfigDict, Field

from app.domain.models import Role


class LoginRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"example": {"email": "aigul@luwo.test", "password": "demo1234"}}
    )

    email: str = Field(max_length=200)
    password: str = Field(max_length=128)


class ProfileResponse(BaseModel):
    user_id: int
    full_name: str
    role: Role
    school_name: str | None = Field(description="None for the superadmin, who is not tied to a school")
    class_names: list[str] = Field(description="Classes a teacher leads; empty for admins")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: ProfileResponse


class ErrorBody(BaseModel):
    code: str = Field(description="authentication_failed, permission_denied, not_found, invalid_request, conflict")
    message: str
    details: dict = {}


class ErrorResponse(BaseModel):
    error: ErrorBody
