from pydantic import BaseModel, Field


class PageState(BaseModel):
    url: str
    title: str
    cleaned_html: str
    has_more_content: bool = False
    error: str | None = None


class SensitiveCheck(BaseModel):
    is_sensitive: bool
    reason: str = ""

class ElementInfo(BaseModel):
    id: str
    tag: str
    role: str | None = None
    type: str | None = None
    text: str = ""
    label: str | None = None
    name: str | None = None
    placeholder: str | None = None
    value: str | None = None
    href: str | None = None
    visible: bool = True
    enabled: bool = True
    checked: bool | None = None
    selected: bool | None = None
    aria_checked: str | None = None
    aria_selected: str | None = None
    in_viewport: bool = False
    rect: dict | None = None
    context: str | None = None
    row_index: int | None = None
    container_id: str | None = None
    container_role: str | None = None
    fingerprint: str | None = None


class ContainerState(BaseModel):
    id: str
    role: str
    selector_hint: str = ""
    selected_count: int = 0
    checked_count: int = 0
    total_items: int = 0


class DialogInfo(BaseModel):
    type: str
    text: str


class ToastInfo(BaseModel):
    text: str
    visible: bool = True


class TextBlock(BaseModel):
    location: str
    text: str


class SnapshotState(BaseModel):
    url: str
    title: str
    containers: list[ContainerState] = Field(default_factory=list)
    dialogs: list[DialogInfo] = Field(default_factory=list)
    toasts: list[ToastInfo] = Field(default_factory=list)
    text_blocks: list[TextBlock] = Field(default_factory=list)
    focused_element: str | None = None


class Snapshot(BaseModel):
    snapshot_id: str
    elements: list[ElementInfo]
    state: SnapshotState
    viewport: dict | None = None
    total_elements: int = 0
    error: str | None = None


class VerificationResult(BaseModel):
    passed: bool
    details: str = ""
    expected: dict | None = None
    actual: dict | None = None