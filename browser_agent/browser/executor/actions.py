import asyncio
from typing import Any

from playwright.async_api import Page, ElementHandle

from browser_agent.browser.executor.exceptions import (
    ElementNotFoundError,
    LiveValidationError,
    SnapshotStaleError,
)
from browser_agent.browser.executor.snapshot import SnapshotManager
from browser_agent.browser.executor.validator import ActionValidator
from browser_agent.config import BrowserSettings
from browser_agent.models import (
    ActionResult,
    AgentAction,
    Click,
    ElementInfo,
    Navigate,
    Scroll,
    Type,
    Wait,
)


class ActionExecutor:
    def __init__(
        self,
        page: Page,
        snapshot_mgr: SnapshotManager,
        validator: ActionValidator,
        settings: BrowserSettings,
    ) -> None:
        self._page = page
        self._snapshot_mgr = snapshot_mgr
        self._validator = validator
        self._settings = settings

    async def execute(self, action: AgentAction) -> ActionResult:
        if isinstance(action, Click):
            return await self._execute_click(action)

        if isinstance(action, Type):
            return await self._execute_type(action)

        if isinstance(action, Navigate):
            return await self._execute_navigate(action)

        if isinstance(action, Scroll):
            return await self._execute_scroll(action)

        if isinstance(action, Wait):
            return await self._execute_wait(action)

        return ActionResult(
            success=False,
            message=f"Unsupported action: {action.action}",
        )

    async def _execute_click(self, action: Click) -> ActionResult:
        handle: ElementHandle | None = None

        try:
            el_info = self._snapshot_mgr.get_element_data(action.element_id)

            selection_error = self._validate_selection_action(action, el_info)
            if selection_error:
                return ActionResult(success=False, message=selection_error)

            if self._is_already_in_target_checked_state(action, el_info):
                target = action.expected.target_checked
                current = self._is_checked(el_info)

                return ActionResult(
                    success=True,
                    message=f"Skip click: {action.element_id} already in target state",
                    observation=f"checked={current}, target={target}",
                    verification_passed=True,
                )

            required_state_error = self._validate_required_state(action)
            if required_state_error:
                return ActionResult(success=False, message=required_state_error)

            is_hidden_selection = self._is_hidden_selection_control(el_info)

            handle = await self._snapshot_mgr.resolve_element(
                action.element_id,
                action.snapshot_id,
                skip_visibility=is_hidden_selection,
            )

            if is_hidden_selection:
                await handle.evaluate("(el) => el.click()")
            else:
                await handle.scroll_into_view_if_needed(timeout=3000)
                await handle.click(timeout=self._settings.PAGE_TIMEOUT)

            await self._wait_for_stable()

            result = ActionResult(
                success=True,
                message=f"Clicked {action.element_id}: {action.description}",
            )

        except (SnapshotStaleError, ElementNotFoundError, LiveValidationError) as exc:
            return ActionResult(success=False, message=str(exc))

        except Exception as exc:
            return ActionResult(
                success=False,
                message=f"Click failed on {action.element_id}",
                error=str(exc),
            )

        finally:
            if handle is not None:
                await self._snapshot_mgr.invalidate(cleanup_dom=True)

        return await self._apply_expected_validation(
            result=result,
            expected=action.expected,
            element_id=action.element_id,
        )

    async def _execute_type(self, action: Type) -> ActionResult:
        handle: ElementHandle | None = None
        try:
            handle = await self._snapshot_mgr.resolve_element(
                action.element_id,
                action.snapshot_id,
            )

            el_info = self._snapshot_mgr.get_element_data(action.element_id)
            fillable_error = self._validate_fillable(action.element_id, el_info)

            if fillable_error:
                return ActionResult(
                    success=False,
                    message=fillable_error,
                )

            if action.clear_first:
                await handle.fill(action.text, timeout=self._settings.PAGE_TIMEOUT)
            else:
                await handle.click(timeout=self._settings.PAGE_TIMEOUT)
                await self._page.keyboard.type(action.text, delay=20)

            if action.press_enter:
                await self._page.keyboard.press("Enter")

            await self._wait_for_stable()

            result = ActionResult(
                success=True,
                message=f"Typed into {action.element_id}: {action.description}",
            )

        except (SnapshotStaleError, ElementNotFoundError, LiveValidationError) as exc:
            return ActionResult(
                success=False,
                message=str(exc),
            )
        except Exception as exc:
            return ActionResult(
                success=False,
                message=f"Type failed on {action.element_id}",
                error=str(exc),
            )
        finally:
            if handle is not None:
                await self._snapshot_mgr.invalidate(cleanup_dom=True)

        return await self._apply_expected_validation(
            result=result,
            expected=action.expected,
            element_id=action.element_id,
        )

    async def _execute_navigate(self, action: Navigate) -> ActionResult:
        try:
            await self._page.goto(
                action.url,
                timeout=30000,
                wait_until="domcontentloaded",
            )
            return ActionResult(
                success=True,
                message=f"Navigated to {action.url}",
            )
        except Exception as exc:
            return ActionResult(
                success=False,
                message="Navigation failed",
                error=str(exc),
            )
        finally:
            await self._snapshot_mgr.invalidate(cleanup_dom=True)

    async def _execute_scroll(self, action: Scroll) -> ActionResult:
        try:
            delta = action.amount * 100
            if action.direction == "up":
                delta = -delta

            await self._page.evaluate("(delta) => window.scrollBy(0, delta)", delta)

            return ActionResult(
                success=True,
                message=f"Scrolled {action.direction}",
            )
        except Exception as exc:
            return ActionResult(
                success=False,
                message="Scroll failed",
                error=str(exc),
            )
        finally:
            await self._snapshot_mgr.invalidate(cleanup_dom=True)

    async def _execute_wait(self, action: Wait) -> ActionResult:
        try:
            await asyncio.sleep(action.seconds)
            return ActionResult(
                success=True,
                message=f"Waited {action.seconds}s",
            )
        finally:
            await self._snapshot_mgr.invalidate(cleanup_dom=True)

    async def _apply_expected_validation(
        self,
        *,
        result: ActionResult,
        expected: Any | None,
        element_id: str | None,
    ) -> ActionResult:
        if expected is None:
            return result

        verification = await self._validator.validate(
            expected,
            element_id,
        )

        result.verification_passed = verification.passed
        result.observation = verification.details
        result.after_state = verification.actual

        if not verification.passed:
            result.success = False

        return result

    def _validate_required_state(self, action: Click) -> str | None:
        if action.required_state is None:
            return None

        snapshot = self._snapshot_mgr.current_snapshot
        if snapshot is None:
            return "Required state cannot be checked: no current snapshot"

        if action.required_state.selected_count is not None:
            actual = self._snapshot_mgr.count_selected(
                snapshot,
                action.required_state.container_id,
            ) or 0
            expected = action.required_state.selected_count

            if actual != expected:
                return (
                    "Required state not met: "
                    f"expected selected_count={expected}, got {actual}"
                )

        return None

    @staticmethod
    def _is_already_in_target_checked_state(
        action: Click,
        el_info: ElementInfo | None,
    ) -> bool:
        if el_info is None:
            return False

        if action.expected is None:
            return False

        if action.expected.target_checked is None:
            return False

        return ActionExecutor._is_checked(el_info) == action.expected.target_checked

    @staticmethod
    def _is_checked(el_info: ElementInfo | None) -> bool:
        if el_info is None:
            return False

        return el_info.checked is True or el_info.aria_checked == "true"

    @staticmethod
    def _validate_fillable(
        element_id: str,
        el_info: ElementInfo | None,
    ) -> str | None:
        if el_info is None:
            return f"Element data for {element_id} not found"

        tag = el_info.tag.upper()
        role = el_info.role
        el_type = (el_info.type or "").lower()

        fillable_input_types = {
            "",
            "text",
            "search",
            "email",
            "password",
            "url",
            "tel",
            "number",
        }

        if tag == "TEXTAREA":
            return None

        if role == "textbox":
            return None

        if tag == "INPUT" and el_type in fillable_input_types:
            return None

        return (
            f"Element {element_id} is not fillable: "
            f"tag={el_info.tag}, type={el_info.type}, role={el_info.role}"
        )

    @staticmethod
    def _validate_selection_action(
        action: Click,
        element: ElementInfo | None,
    ) -> str | None:
        if not action.expected or action.expected.target_checked is None:
            return None

        if element is None:
            return "target_checked requires element data"

        if (
            not ActionExecutor._is_checkable(element)
            and not element.is_selection_control
        ):
            return (
                "target_checked requires checkbox-like or selection-control element, "
                f"got tag={element.tag}, role={element.role}, type={element.type}, "
                f"label={element.label!r}"
            )

        intent = action.selection_intent
        if intent is None:
            return "target_checked requires selection_intent: item, range, or all"

        if intent.mode in {"item", "range"}:
            if element.selection_scope != "item":
                return "item/range selection requires selection_scope=item"
            if not element.container_id:
                return "item/range selection requires element.container_id"
            if element.row_index is None:
                return "item/range selection requires element.row_index"

            if intent.container_id and element.container_id != intent.container_id:
                return (
                    "selection_intent.container_id mismatch: "
                    f"expected {intent.container_id}, got {element.container_id}"
                )

        if intent.mode == "all":
            if element.selection_scope != "global":
                return "all selection requires selection_scope=global"

        return None

    @staticmethod
    def _is_checkable(element: ElementInfo) -> bool:
        role = (element.role or "").lower()
        typ = (element.type or "").lower()

        return (
            typ == "checkbox"
            or role in {"checkbox", "menuitemcheckbox", "option"}
            or element.aria_checked is not None
            or element.aria_selected is not None
        )

    @staticmethod
    def _is_hidden_selection_control(
        element: ElementInfo | None,
    ) -> bool:
        return (
            element is not None and element.is_selection_control and not element.visible
        )

    async def _wait_for_stable(self) -> None:
        try:
            await self._page.wait_for_load_state("domcontentloaded", timeout=5000)
            await self._page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass

        await asyncio.sleep(1.0)
