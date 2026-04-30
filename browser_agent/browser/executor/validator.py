from browser_agent.browser.executor.snapshot import SnapshotManager
from browser_agent.models import (
    ElementInfo,
    ExpectedCondition,
    Snapshot,
    VerificationResult,
)


class ActionValidator:
    def __init__(self, snapshot_mgr: SnapshotManager) -> None:
        self._snapshot_mgr = snapshot_mgr

    async def validate(
        self,
        expected: ExpectedCondition,
        element_id: str | None = None,
    ) -> VerificationResult:
        snapshot = await self._snapshot_mgr.take_snapshot()
        elements_by_id = {el.id: el for el in snapshot.elements}

        checks: list[tuple[str, bool]] = []
        actual: dict = {}

        target_element = elements_by_id.get(element_id) if element_id else None

        self._validate_target_checked(
            expected=expected,
            element_id=element_id,
            element=target_element,
            checks=checks,
            actual=actual,
        )

        self._validate_element_value(
            expected=expected,
            element_id=element_id,
            element=target_element,
            checks=checks,
            actual=actual,
        )

        self._validate_selected_count(
            expected=expected,
            snapshot=snapshot,
            checks=checks,
            actual=actual,
        )

        self._validate_url_contains(
            expected=expected,
            snapshot=snapshot,
            checks=checks,
            actual=actual,
        )

        self._validate_text_visible(
            expected=expected,
            snapshot=snapshot,
            checks=checks,
            actual=actual,
        )

        if not checks:
            return VerificationResult(
                passed=False,
                details="No expected checks were provided",
                expected=expected.model_dump(exclude_none=True),
                actual=actual,
            )

        passed = all(ok for _, ok in checks)
        failed = [name for name, ok in checks if not ok]

        return VerificationResult(
            passed=passed,
            details="All checks passed" if passed else f"Failed: {', '.join(failed)}",
            expected=expected.model_dump(exclude_none=True),
            actual=actual,
        )

    @staticmethod
    def _validate_target_checked(
        *,
        expected: ExpectedCondition,
        element_id: str | None,
        element: ElementInfo | None,
        checks: list[tuple[str, bool]],
        actual: dict,
    ) -> None:
        if expected.target_checked is None:
            return

        if not element_id:
            actual["checked"] = "element_id is required"
            checks.append(("target_checked", False))
            return

        if element is None:
            actual["checked"] = "element not found"
            checks.append(("target_checked", False))
            return

        is_checked = element.checked is True or element.aria_checked == "true"
        actual["checked"] = is_checked
        checks.append(("target_checked", is_checked == expected.target_checked))

    @staticmethod
    def _validate_element_value(
        *,
        expected: ExpectedCondition,
        element_id: str | None,
        element: ElementInfo | None,
        checks: list[tuple[str, bool]],
        actual: dict,
    ) -> None:
        if expected.element_value is None:
            return

        if not element_id:
            actual["value"] = "element_id is required"
            checks.append(("element_value", False))
            return

        if element is None:
            actual["value"] = "element not found"
            checks.append(("element_value", False))
            return

        actual["value"] = element.value
        checks.append(("element_value", element.value == expected.element_value))

    def _validate_selected_count(
        self,
        *,
        expected: ExpectedCondition,
        snapshot: Snapshot,
        checks: list[tuple[str, bool]],
        actual: dict,
    ) -> None:
        if expected.selected_count is None:
            return

        count = self._snapshot_mgr.count_selected(
            snapshot,
            expected.container_id,
        )

        actual["selected_count"] = count

        if count is None:
            checks.append(("selected_count", False))
            actual["selected_count_error"] = (
                f"Container {expected.container_id} not found"
            )
            return

        checks.append(("selected_count", count == expected.selected_count))

    @staticmethod
    def _validate_url_contains(
        *,
        expected: ExpectedCondition,
        snapshot: Snapshot,
        checks: list[tuple[str, bool]],
        actual: dict,
    ) -> None:
        if expected.url_contains is None:
            return

        url = snapshot.state.url
        actual["url"] = url
        checks.append(("url_contains", expected.url_contains in url))

    @staticmethod
    def _validate_text_visible(
        *,
        expected: ExpectedCondition,
        snapshot: Snapshot,
        checks: list[tuple[str, bool]],
        actual: dict,
    ) -> None:
        if expected.text_visible is None:
            return

        found = ActionValidator._find_text(snapshot, expected.text_visible)
        actual["text_found"] = found
        checks.append(("text_visible", found))

    @staticmethod
    def _find_text(snapshot: Snapshot, text: str) -> bool:
        needle = text.lower()

        for block in snapshot.state.text_blocks:
            if needle in block.text.lower():
                return True

        for dialog in snapshot.state.dialogs:
            if needle in dialog.text.lower():
                return True

        for toast in snapshot.state.toasts:
            if needle in toast.text.lower():
                return True

        for element in snapshot.elements:
            values = [
                element.text,
                element.label,
                element.context,
                element.value,
            ]
            if any(value and needle in value.lower() for value in values):
                return True

        return False
