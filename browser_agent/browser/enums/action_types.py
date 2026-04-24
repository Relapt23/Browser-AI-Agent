from enum import Enum


class ActionType(str, Enum):
    CLICK = "click"
    TYPE = "type"
    NAVIGATE = "navigate"
    SCROLL = "scroll"
    WAIT = "wait"

    @property
    def handler(self) -> str:
        return f"_do_{self.value}"