from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class Click(BaseModel):
    action: Literal["click"] = "click"
    selector: str
    description: str = Field(description="What this click is intended to do")
    is_sensitive: bool = Field(
        default=False,
        description="True if this action involves payment, personal data, order confirmation, CAPTCHA, 2FA, or data deletion",
    )


class Type(BaseModel):
    action: Literal["type"] = "type"
    selector: str
    text: str = Field(description="Text to type into the element")
    clear_first: bool = Field(default=True, description="Clear existing text before typing")
    press_enter: bool = Field(default=False, description="Press Enter after typing")
    description: str = Field(description="What this typing is intended to do")
    is_sensitive: bool = Field(
        default=False,
        description="True if this action involves payment, personal data, order confirmation, CAPTCHA, 2FA, or data deletion",
    )


class Navigate(BaseModel):
    action: Literal["navigate"] = "navigate"
    url: str = Field(description="URL to navigate to")
    description: str = Field(description="Why navigating to this URL")
    is_sensitive: bool = Field(
        default=False,
        description="True if this action involves payment, personal data, order confirmation, CAPTCHA, 2FA, or data deletion",
    )


class Scroll(BaseModel):
    action: Literal["scroll"] = "scroll"
    direction: Literal["up", "down"] = "down"
    amount: int = Field(default=3, description="Pixels to scroll (multiplied by 100)")
    description: str = Field(description="Why scrolling")


class Wait(BaseModel):
    action: Literal["wait"] = "wait"
    seconds: float = Field(default=2.0, ge=0.5, le=10.0)
    description: str = Field(description="What we are waiting for")


class AskUser(BaseModel):
    action: Literal["ask_user"] = "ask_user"
    question: str = Field(description="Question to ask the user")


class Done(BaseModel):
    action: Literal["done"] = "done"
    summary: str = Field(description="Summary of what was accomplished")
    success: bool = True


AgentAction = Annotated[
    Union[Click, Type, Navigate, Scroll, Wait, AskUser, Done],
    Field(discriminator="action"),
]