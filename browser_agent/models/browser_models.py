from pydantic import BaseModel


class InteractiveElement(BaseModel):
    index: int
    tag: str
    role: str
    name: str
    type: str | None = None
    value: str | None = None
    href: str | None = None
    placeholder: str | None = None


class PageState(BaseModel):
    url: str
    title: str
    visible_text: str
    interactive_elements: list[InteractiveElement]
    has_more_content: bool = False
    error: str | None = None


class SensitiveCheck(BaseModel):
    is_sensitive: bool
    reason: str = ""
