from uuid import UUID
from pydantic import Field
from .camel_base_model import CamelCaseBaseModel as BaseModel


class UserResponse(BaseModel):
    """User response schema"""

    id: str | UUID = Field(..., description="User ID")
    username: str = Field(..., description="Username")
    first_name: str = Field(..., description="First name")
    last_name: str = Field(..., description="Last name")
    user_type: str = Field(..., description="User type")
    is_active: bool = Field(..., description="User active status")

    class Config:
        from_attributes = True
