from pydantic import BaseModel


class LoginRequest(BaseModel):
    # Plain str, not pydantic's EmailStr -- that needs the extra
    # email-validator dependency and login only needs an exact match against
    # the stored email, not RFC validation.
    email: str
    password: str


class UserResponse(BaseModel):
    id: str
    email: str


class MeResponse(UserResponse):
    role: str
    client_ids: list[str]
