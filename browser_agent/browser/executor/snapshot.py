from pathlib import Path
from typing import Any
from browser_agent.browser.executor.exceptions import (
    SnapshotStaleError,
    ElementNotFoundError,
    LiveValidationError,
)
from playwright.async_api import ElementHandle, Page

from browser_agent.config import BrowserSettings
from browser_agent.models import ElementInfo, Snapshot, SnapshotState


_JS_CODE: str | None = None
_SNAP_ATTR = "data-agent-snapshot-id"


def _load_js() -> str:
    global _JS_CODE

    if _JS_CODE is None:
        js_path = Path(__file__).parent / "js" / "snapshot_extractor.js"
        _JS_CODE = js_path.read_text(encoding="utf-8")

    return _JS_CODE


class SnapshotManager:
    def __init__(self, page: Page, settings: BrowserSettings) -> None:
        self._page = page
        self._settings = settings

        self._current_snapshot_id: str | None = None
        self._element_handles: dict[str, ElementHandle] = {}
        self._element_data: dict[str, ElementInfo] = {}
        self._snapshot: Snapshot | None = None

    @property
    def current_snapshot_id(self) -> str | None:
        return self._current_snapshot_id

    @property
    def current_snapshot(self) -> Snapshot | None:
        return self._snapshot

    async def take_snapshot(self) -> Snapshot:
        await self.invalidate(cleanup_dom=True)

        raw = await self._evaluate_snapshot_script()

        element_handles = await self._collect_element_handles()

        elements, element_data = self._parse_elements(raw)

        missing_handles = self._find_missing_handles(element_data, element_handles)

        snapshot = self._build_snapshot(raw, elements, missing_handles)

        self._set_current_snapshot(
            snapshot=snapshot,
            element_handles=element_handles,
            element_data=element_data,
        )

        return snapshot

    async def resolve_element(
        self,
        element_id: str,
        snapshot_id: str,
    ) -> ElementHandle:
        self._check_current_snapshot_id(snapshot_id)

        handle = self._get_handle_or_raise(element_id)
        element_info = self._get_element_info_or_raise(element_id)

        await self._live_validate(handle, element_id, element_info)

        return handle

    async def _live_validate(
        self,
        handle: ElementHandle,
        element_id: str,
        el_info: ElementInfo,
    ) -> None:
        live = await self._read_live_element_state(handle, element_id)

        self._validate_live_basics(
            element_id=element_id,
            live=live,
        )

        self._validate_fingerprint(
            element_id=element_id,
            el_info=el_info,
            live=live,
        )

    def _validate_fingerprint(
        self,
        element_id: str,
        el_info: ElementInfo,
        live: dict[str, Any],
    ) -> None:
        if live.get("tag") != el_info.tag:
            raise LiveValidationError(
                f"Element {element_id} tag changed: "
                f"expected {el_info.tag}, got {live.get('tag')}"
            )

        if el_info.role and live.get("role") != el_info.role:
            raise LiveValidationError(
                f"Element {element_id} role changed: "
                f"expected {el_info.role}, got {live.get('role')}"
            )

        if el_info.type and live.get("type") != el_info.type:
            raise LiveValidationError(
                f"Element {element_id} type changed: "
                f"expected {el_info.type}, got {live.get('type')}"
            )

        if el_info.name and live.get("name") != el_info.name:
            raise LiveValidationError(
                f"Element {element_id} name changed: "
                f"expected {el_info.name}, got {live.get('name')}"
            )

    def get_element_data(self, element_id: str) -> ElementInfo | None:
        return self._element_data.get(element_id)

    def get_snapshot(self) -> Snapshot | None:
        return self._snapshot

    async def cleanup_dom_marks(self) -> None:
        try:
            await self._page.evaluate(
                """snapAttr => {
                    document
                        .querySelectorAll(`[${snapAttr}]`)
                        .forEach(el => el.removeAttribute(snapAttr));
                }""",
                _SNAP_ATTR,
            )
        except Exception:
            pass

    async def invalidate(self, *, cleanup_dom: bool = False) -> None:
        for handle in self._element_handles.values():
            try:
                await handle.dispose()
            except Exception:
                pass

        self._element_handles.clear()
        self._element_data.clear()
        self._snapshot = None
        self._current_snapshot_id = None

        if cleanup_dom:
            await self.cleanup_dom_marks()

    async def _evaluate_snapshot_script(self) -> dict[str, Any]:
        return await self._page.evaluate(_load_js())

    async def _collect_element_handles(self) -> dict[str, ElementHandle]:
        handles = await self._page.query_selector_all(f"[{_SNAP_ATTR}]")

        result: dict[str, ElementHandle] = {}

        for handle in handles:
            element_id = await handle.get_attribute(_SNAP_ATTR)
            if element_id:
                result[element_id] = handle

        return result

    def _parse_elements(
        self,
        raw: dict[str, Any],
    ) -> tuple[list[ElementInfo], dict[str, ElementInfo]]:
        elements: list[ElementInfo] = []
        element_data: dict[str, ElementInfo] = {}

        for item in raw.get("elements", []):
            element = ElementInfo(**item)
            elements.append(element)
            element_data[element.id] = element

        return elements, element_data

    def _build_snapshot_state(self, raw: dict[str, Any]) -> SnapshotState:
        state_raw = raw.get("state", {}) or {}

        return SnapshotState(
            **state_raw,
            url=raw.get("url", ""),
            title=raw.get("title", ""),
        )

    def _build_snapshot(
        self,
        raw: dict[str, Any],
        elements: list[ElementInfo],
        missing_handles: list[str],
    ) -> Snapshot:
        return Snapshot(
            snapshot_id=raw["snapshot_id"],
            elements=elements,
            state=self._build_snapshot_state(raw),
            viewport=raw.get("viewport"),
            total_elements=len(elements),
            error=self._format_missing_handles_error(missing_handles),
        )

    def _check_current_snapshot_id(self, snapshot_id):
        if snapshot_id != self._current_snapshot_id:
            raise SnapshotStaleError(
                f"Snapshot {snapshot_id} is stale; current snapshot is {self._current_snapshot_id}"
            )

    def _get_handle_or_raise(self, element_id: str) -> ElementHandle:
        handle = self._element_handles.get(element_id)

        if handle is None:
            raise ElementNotFoundError(
                f"Element {element_id} not found in current snapshot"
            )

        return handle

    def _get_element_info_or_raise(self, element_id: str) -> ElementInfo:
        element_info = self._element_data.get(element_id)

        if element_info is None:
            raise ElementNotFoundError(f"Element data for {element_id} not found")

        return element_info

    async def _read_live_element_state(
        self,
        handle: ElementHandle,
        element_id: str,
    ) -> dict[str, Any]:
        try:
            return await handle.evaluate(
                """(el, snapAttr) => {
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();

                    const getLabel = () => {
                        const ariaLabel = el.getAttribute('aria-label');
                        if (ariaLabel) return ariaLabel;

                        const id = el.id;
                        if (id) {
                            const labelEl = document.querySelector(
                                `label[for="${CSS.escape(id)}"]`
                            );
                            if (labelEl) return labelEl.textContent?.trim() || null;
                        }

                        const parentLabel = el.closest('label');
                        if (parentLabel) {
                            return parentLabel.textContent?.trim() || null;
                        }

                        const labelledBy = el.getAttribute('aria-labelledby');
                        if (labelledBy) {
                            const labelEl = document.getElementById(labelledBy);
                            if (labelEl) return labelEl.textContent?.trim() || null;
                        }

                        return null;
                    };

                    return {
                        connected: el.isConnected,
                        snapshotMarker: el.getAttribute(snapAttr),

                        tag: el.tagName,
                        role: el.getAttribute('role') || null,
                        type: el.getAttribute('type') || null,
                        name: el.getAttribute('name') || null,
                        label: getLabel(),
                        text: (
                            el.innerText ||
                            el.textContent ||
                            el.value ||
                            ''
                        ).trim().slice(0, 200),

                        visible:
                            style.display !== 'none' &&
                            style.visibility !== 'hidden' &&
                            parseFloat(style.opacity) !== 0 &&
                            rect.width > 0 &&
                            rect.height > 0,

                        disabled:
                            el.disabled === true ||
                            el.getAttribute('aria-disabled') === 'true',

                        rect: {
                            x: Math.round(rect.x),
                            y: Math.round(rect.y),
                            width: Math.round(rect.width),
                            height: Math.round(rect.height)
                        }
                    };
                }""",
                _SNAP_ATTR,
            )
        except Exception as exc:
            raise LiveValidationError(
                f"Element {element_id} is detached or inaccessible: {exc}"
            ) from exc

    def _set_current_snapshot(
        self,
        *,
        snapshot: Snapshot,
        element_handles: dict[str, ElementHandle],
        element_data: dict[str, ElementInfo],
    ) -> None:
        self._current_snapshot_id = snapshot.snapshot_id
        self._element_handles = element_handles
        self._element_data = element_data
        self._snapshot = snapshot

    @staticmethod
    def _find_missing_handles(
        element_data: dict[str, ElementInfo],
        element_handles: dict[str, ElementHandle],
    ) -> list[str]:
        return sorted(set(element_data) - set(element_handles))

    @staticmethod
    def _format_missing_handles_error(missing_handles: list[str]) -> str | None:
        if not missing_handles:
            return None

        shown = ", ".join(missing_handles[:20])
        suffix = "..." if len(missing_handles) > 20 else ""

        return f"Missing handles for elements: {shown}{suffix}"

    @staticmethod
    def _validate_live_basics(
        *,
        element_id: str,
        live: dict[str, Any],
    ) -> None:
        if not live.get("connected"):
            raise LiveValidationError(f"Element {element_id} is detached from DOM")

        marker = live.get("snapshotMarker")
        if marker != element_id:
            raise LiveValidationError(
                f"Element {element_id} snapshot marker mismatch: "
                f"expected {element_id}, got {marker}"
            )

        if not live.get("visible"):
            raise LiveValidationError(f"Element {element_id} is not visible")

        if live.get("disabled"):
            raise LiveValidationError(f"Element {element_id} is disabled")
