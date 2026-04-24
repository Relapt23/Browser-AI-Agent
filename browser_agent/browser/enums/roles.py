from enum import Enum


class AriaRole(str, Enum):
    LINK = "link"
    BUTTON = "button"
    TEXTBOX = "textbox"
    COMBOBOX = "combobox"
    TAB = "tab"
    MENUITEM = "menuitem"


TAG_TO_ROLE: dict[str, AriaRole] = {
    "a": AriaRole.LINK,
    "button": AriaRole.BUTTON,
    "input": AriaRole.TEXTBOX,
    "textarea": AriaRole.TEXTBOX,
    "select": AriaRole.COMBOBOX,
}