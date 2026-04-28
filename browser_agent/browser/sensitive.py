import re

from browser_agent.models import (
    AgentAction,
    Click,
    Navigate,
    SensitiveCheck,
    Snapshot,
    Type,
    ElementInfo,
)


_SENSITIVE_URL_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\bcheckout\b",
        r"\bpayment\b",
        r"\bpay\b",
        r"\bbilling\b",
        r"order/confirm",
        r"\bpurchase\b",
        r"\bsubscribe\b",
    ]
]

_SENSITIVE_TEXT_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\bpay\b",
        r"\bbuy\b",
        r"\bcheckout\b",
        r"\bplace order\b",
        r"\bconfirm order\b",
        r"\bsubscribe\b",
        r"оплатить",
        r"купить",
        r"оформить заказ",
        r"подтвердить заказ",
        r"заказать",
    ]
]

_CAPTCHA_URL_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"google\.com/sorry",
        r"captcha",
        r"challenge",
        r"recaptcha",
        r"hcaptcha",
    ]
]

_CAPTCHA_TEXT_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"captcha",
        r"verify you.?re.? human",
        r"not a robot",
        r"подтвердите.+что вы не робот",
        r"проверк[аиу].+безопасности",
    ]
]


class SensitiveDetector:
    @staticmethod
    def check_action(
        action: AgentAction,
        snapshot: Snapshot,
    ) -> SensitiveCheck:
        if getattr(action, "is_sensitive", False):
            description = getattr(action, "description", action.action)
            return SensitiveCheck(
                is_sensitive=True,
                reason=f"LLM flagged as sensitive: {description}",
            )

        if isinstance(action, (Click, Type)):
            elements_by_id = SensitiveDetector._elements_by_id(snapshot)
            element = elements_by_id.get(action.element_id)

            if element and (element.type or "").lower() == "password":
                return SensitiveCheck(
                    is_sensitive=True,
                    reason="Interacting with a password field",
                )

            if isinstance(action, Click) and element:
                element_text = " ".join(
                    value
                    for value in [
                        element.text,
                        element.label,
                        element.context,
                        element.value,
                    ]
                    if value
                )

                for pattern in _SENSITIVE_TEXT_PATTERNS:
                    if pattern.search(element_text):
                        return SensitiveCheck(
                            is_sensitive=True,
                            reason=f"Clicking sensitive element: {element_text[:120]}",
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
    def check_page(snapshot: Snapshot) -> SensitiveCheck:
        for pattern in _SENSITIVE_URL_PATTERNS:
            if pattern.search(snapshot.state.url):
                return SensitiveCheck(
                    is_sensitive=True,
                    reason=f"Sensitive URL detected: {snapshot.state.url}",
                )

        return SensitiveCheck(is_sensitive=False)

    @staticmethod
    def check_captcha(snapshot: Snapshot) -> bool:
        url = snapshot.state.url

        for pattern in _CAPTCHA_URL_PATTERNS:
            if pattern.search(url):
                return True

        text = SensitiveDetector._snapshot_text(snapshot)

        return any(pattern.search(text) for pattern in _CAPTCHA_TEXT_PATTERNS)

    @staticmethod
    def _elements_by_id(snapshot: Snapshot) -> dict[str, ElementInfo]:
        return {element.id: element for element in snapshot.elements}

    @staticmethod
    def _snapshot_text(snapshot: Snapshot) -> str:
        parts: list[str] = []

        parts.extend(block.text for block in snapshot.state.text_blocks)
        parts.extend(dialog.text for dialog in snapshot.state.dialogs)
        parts.extend(toast.text for toast in snapshot.state.toasts)

        for element in snapshot.elements:
            parts.extend(
                value
                for value in [
                    element.text,
                    element.label,
                    element.context,
                    element.value,
                ]
                if value
            )

        return " ".join(parts)
