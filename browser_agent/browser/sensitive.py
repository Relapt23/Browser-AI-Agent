import re

from browser_agent.models import (
    AgentAction,
    Click,
    InteractiveElement,
    Navigate,
    PageState,
    SensitiveCheck,
    Type,
)


_SENSITIVE_URL_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"checkout",
        r"payment",
        r"pay\b",
        r"billing",
        r"order/confirm",
        r"purchase",
        r"subscribe",
    ]
]


class SensitiveDetector:
    @staticmethod
    def check_page(page_state: PageState) -> SensitiveCheck:
        for pattern in _SENSITIVE_URL_PATTERNS:
            if pattern.search(page_state.url):
                return SensitiveCheck(
                    is_sensitive=True,
                    reason=f"Sensitive URL detected: {page_state.url}",
                )
        return SensitiveCheck(is_sensitive=False)

    def check_action(
        self,
        action: AgentAction,
        elements: list[InteractiveElement],
    ) -> SensitiveCheck:
        if isinstance(action, (Click, Type, Navigate)) and action.is_sensitive:
            return SensitiveCheck(
                is_sensitive=True,
                reason=f"LLM flagged as sensitive: {action.description}",
            )

        if isinstance(action, (Click, Type)):
            element = self._find_element(action.selector, elements)
            if element and element.type == "password":
                return SensitiveCheck(
                    is_sensitive=True,
                    reason="Interacting with a password field",
                )

        if isinstance(action, Navigate):
            for pattern in _SENSITIVE_URL_PATTERNS:
                if pattern.search(action.url):
                    return SensitiveCheck(
                        is_sensitive=True,
                        reason=f"Navigating to sensitive URL: {action.url}",
                    )

        return SensitiveCheck(is_sensitive=False)

    @staticmethod
    def _find_element(
        selector: str,
        elements: list[InteractiveElement],
    ) -> InteractiveElement | None:
        match = re.match(r"\[(\d+)]", selector)
        if match:
            idx = int(match.group(1))
            if 0 <= idx < len(elements):
                return elements[idx]
        return None
