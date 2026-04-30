from browser_agent.models import ElementInfo, Snapshot
from typing import NamedTuple


class ElementRank(NamedTuple):
    in_viewport: int
    in_active_container: int
    is_interactive: int
    has_content: int


class SnapshotMapper:
    IMPORTANT_ROLES = {
        "button",
        "checkbox",
        "textbox",
        "link",
        "tab",
        "option",
        "radio",
        "menuitem",
    }
    IMPORTANT_TAGS = {"INPUT", "TEXTAREA", "SELECT", "BUTTON", "A"}

    def __init__(
        self,
        max_elements: int = 200,
        max_text_blocks: int = 5,
    ) -> None:
        self._max_elements = max_elements
        self._max_text_blocks = max_text_blocks

    def to_llm_view(self, snapshot: Snapshot) -> str:
        parts = [
            self._format_header(snapshot),
            self._format_state(snapshot),
            self._format_elements(snapshot),
            self._format_text_blocks(snapshot),
            self._format_diagnostics(snapshot),
        ]
        return "\n\n".join(part for part in parts if part)

    def _format_header(self, snapshot: Snapshot) -> str:
        lines = [
            f"--- Snapshot {snapshot.snapshot_id} ---",
            f"URL: {snapshot.state.url}",
            f"Title: {snapshot.state.title}",
        ]

        if snapshot.viewport:
            width = snapshot.viewport.get("width", "?")
            height = snapshot.viewport.get("height", "?")
            lines.append(f"Viewport: {width}x{height}")

        return "\n".join(lines)

    def _format_state(self, snapshot: Snapshot) -> str:
        lines = ["State:"]

        if snapshot.state.containers:
            lines.append("- Containers:")
            for container in snapshot.state.containers:
                hint = (
                    f' "{self._truncate(container.selector_hint, 80)}"'
                    if container.selector_hint
                    else ""
                )
                lines.append(
                    f"  {container.id} {container.role}{hint}: "
                    f"selected={container.selected_count} "
                    f"checked={container.checked_count} "
                    f"total={container.total_items}"
                )
        else:
            lines.append("- Containers: none")

        if snapshot.state.dialogs:
            lines.append("- Dialogs:")
            for dialog in snapshot.state.dialogs:
                lines.append(f'  {dialog.type}: "{self._truncate(dialog.text, 200)}"')
        else:
            lines.append("- Dialogs: none")

        if snapshot.state.toasts:
            lines.append("- Toasts:")
            for toast in snapshot.state.toasts:
                lines.append(f'  "{self._truncate(toast.text, 200)}"')
        else:
            lines.append("- Toasts: none")

        lines.append(f"- Focused: {snapshot.state.focused_element or 'none'}")

        return "\n".join(lines)

    def _format_elements(self, snapshot: Snapshot) -> str:
        visible_elements = [
            element for element in snapshot.elements
            if element.visible or element.is_selection_control
        ]
        selected_elements = self._select_elements(visible_elements, snapshot)

        suffix = (
            " (truncated)" if len(selected_elements) < len(visible_elements) else ""
        )
        lines = [
            f"Elements shown: {len(selected_elements)} of {len(visible_elements)} visible, {len(snapshot.elements)} total{suffix}",
            "",
        ]

        for container_id, elements in self._group_by_container(
            selected_elements,
            snapshot,
        ):
            lines.append(self._format_container_header(container_id, snapshot))
            for element in elements:
                lines.append("  " + self._format_element(element))

        return "\n".join(lines)

    def _select_elements(
        self,
        visible_elements: list[ElementInfo],
        snapshot: Snapshot,
    ) -> list[ElementInfo]:
        containers_with_state = {
            container.id
            for container in snapshot.state.containers
            if container.checked_count > 0 or container.selected_count > 0
        }

        selection_controls = [
            el for el in visible_elements if el.is_selection_control
        ]
        non_controls = [
            el for el in visible_elements if not el.is_selection_control
        ]

        remaining = max(0, self._max_elements - len(selection_controls))
        ranked = sorted(
            non_controls,
            key=lambda element: self._rank_element(element, containers_with_state),
        )[:remaining]

        return selection_controls + ranked

    @classmethod
    def _rank_element(
        cls,
        element: ElementInfo,
        containers_with_state: set[str],
    ) -> ElementRank:
        role = (element.role or "").lower()
        tag = element.tag.upper()

        return ElementRank(
            in_viewport=0 if element.in_viewport else 1,
            in_active_container=(
                0
                if element.container_id
                and element.container_id in containers_with_state
                else 1
            ),
            is_interactive=(
                0 if role in cls.IMPORTANT_ROLES or tag in cls.IMPORTANT_TAGS else 1
            ),
            has_content=0
            if element.text or element.label or element.placeholder
            else 1,
        )

    def _format_element(self, element: ElementInfo) -> str:
        parts = [element.id, self._element_type_label(element)]

        marker = self._state_marker(element)
        if marker:
            parts.append(marker)

        title = self._element_title(element)
        if title:
            parts.append(title)

        if element.placeholder:
            parts.append(f'placeholder="{self._truncate(element.placeholder, 80)}"')

        if element.value:
            parts.append(self._format_value(element))

        if element.href:
            parts.append(f'href="{self._truncate(element.href, 80)}"')

        if not element.enabled:
            parts.append("disabled")

        if not element.in_viewport:
            parts.append("offscreen")

        if element.row_index is not None:
            parts.append(f"row={element.row_index}")

        if element.container_id:
            parts.append(f"c={element.container_id}")

        if element.context:
            parts.append(f'ctx="{self._truncate(element.context, 160)}"')

        if element.is_selection_control:
            parts.append(f"selection={element.selection_scope or 'unknown'}")
            if not element.visible:
                parts.append("hover-reveal")

        return " ".join(parts)

    @staticmethod
    def _element_type_label(element: ElementInfo) -> str:
        tag = element.tag.lower()
        role = (element.role or "").lower()

        if role and role not in {"presentation", "none"}:
            return f"{role}:{element.type}" if element.type else role

        if tag == "input" and element.type:
            return f"input:{element.type}"

        if tag == "a":
            return "link"

        return tag

    @staticmethod
    def _state_marker(element: ElementInfo) -> str | None:
        if element.checked is True or element.aria_checked == "true":
            return "[x]"

        if element.selected is True or element.aria_selected == "true":
            return "[selected]"

        if (
            element.checked is False
            or (element.type or "").lower() == "checkbox"
            or (element.role or "").lower() == "checkbox"
        ):
            return "[ ]"

        return None

    def _element_title(self, element: ElementInfo) -> str | None:
        if element.label:
            return f'label="{self._truncate(element.label, 80)}"'

        if element.text:
            return f'"{self._truncate(element.text, 80)}"'

        return None

    def _format_value(self, element: ElementInfo) -> str:
        if (element.type or "").lower() == "password":
            return 'value="<hidden>"'

        return f'value="{self._truncate(element.value, 80)}"'

    def _group_by_container(
        self,
        elements: list[ElementInfo],
        snapshot: Snapshot,
    ) -> list[tuple[str | None, list[ElementInfo]]]:
        groups: dict[str | None, list[ElementInfo]] = {}

        for element in elements:
            groups.setdefault(element.container_id, []).append(element)

        known_container_ids = {container.id for container in snapshot.state.containers}
        result: list[tuple[str | None, list[ElementInfo]]] = []

        for container_id in sorted(known_container_ids):
            if container_id in groups:
                result.append((container_id, groups.pop(container_id)))

        for container_id in sorted(
            groups.keys(),
            key=lambda value: (value is None, value or ""),
        ):
            result.append((container_id, groups[container_id]))

        return result

    def _format_container_header(
        self,
        container_id: str | None,
        snapshot: Snapshot,
    ) -> str:
        if container_id is None:
            return "Container none:"

        for container in snapshot.state.containers:
            if container.id == container_id:
                return f"Container {container.id} {container.role}:"

        return f"Container {container_id}:"

    def _format_text_blocks(self, snapshot: Snapshot) -> str:
        blocks = snapshot.state.text_blocks[: self._max_text_blocks]

        if not blocks:
            return ""

        lines = ["Visible text:"]

        for block in blocks:
            lines.append(f'- {block.location}: "{self._truncate(block.text, 300)}"')

        return "\n".join(lines)

    def _format_diagnostics(self, snapshot: Snapshot) -> str:
        lines: list[str] = []

        if snapshot.error:
            lines.append(f"Snapshot warning: {snapshot.error}")

        visible_count = sum(1 for element in snapshot.elements if element.visible)
        hidden_excluded = len(snapshot.elements) - visible_count
        visible_not_shown = max(0, visible_count - self._max_elements)

        if visible_not_shown:
            lines.append(
                f"Note: {visible_not_shown} visible elements not shown. "
                f"Use scroll or search if needed."
            )

        if hidden_excluded:
            lines.append(
                f"Note: {hidden_excluded} hidden elements excluded from LLM view."
            )

        return "\n".join(lines)

    @staticmethod
    def _truncate(text: str | None, limit: int) -> str:
        if not text:
            return ""

        normalized = " ".join(str(text).split()).replace('"', "'")

        if len(normalized) <= limit:
            return normalized

        return normalized[:limit] + "..."
