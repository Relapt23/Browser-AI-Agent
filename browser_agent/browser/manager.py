import asyncio
import re

from playwright.async_api import Browser, BrowserContext, ElementHandle, Page, async_playwright

from browser_agent.browser.enums import TAG_TO_ROLE, ActionType
from browser_agent.config import BrowserSettings

from browser_agent.models import (
    ActionResult,
    AgentAction,
    Click,
    InteractiveElement,
    Navigate,
    PageState,
    Scroll,
    Type,
    Wait,
)

INTERACTIVE_SELECTORS = (
    "a, button, input, textarea, select, "
    "[role='button'], [role='link'], [role='tab'], [role='menuitem']"
)

CONTENT_SELECTORS = ["main", "article", "[role='main']", "#content", ".content", "body"]


class BrowserManager:
    def __init__(self, settings: BrowserSettings) -> None:
        self._settings = settings
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._elements: list[InteractiveElement] = []
        self._handles: list[ElementHandle] = []

    async def __aenter__(self):
        await self.launch()
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def launch(self) -> None:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self._settings.HEADLESS,
            slow_mo=self._settings.SLOW_MO,
        )
        self._context = await self._browser.new_context(
            viewport={
                "width": self._settings.VIEWPORT_WIDTH,
                "height": self._settings.VIEWPORT_HEIGHT,
            },
        )
        self._page = await self._context.new_page()
        await self._context.add_init_script(
            "document.addEventListener('click', e => {"
            "  const a = e.target.closest('a');"
            "  if (a) a.removeAttribute('target');"
            "}, true);"
        )

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    @property
    def page(self) -> Page:
        assert self._page is not None, "Browser not launched"
        return self._page

    @property
    def elements(self) -> list[InteractiveElement]:
        return self._elements

    async def get_page_state(self) -> PageState:
        url = self.page.url
        if url:
            try:
                title = await self.page.title()
                visible_text = await self._extract_visible_text()
                elements = await self._extract_interactive_elements()
                self._elements = elements
                has_more = await self._has_more_content()

                return PageState(
                    url=url,
                    title=title,
                    visible_text=visible_text,
                    interactive_elements=elements,
                    has_more_content=has_more,
                )
            except Exception as e:
                return PageState(
                    url=self.page.url,
                    title="",
                    visible_text="",
                    interactive_elements=[],
                    error=str(e),
                )
        else:
            return PageState(
                url="",
                title="",
                visible_text="",
                interactive_elements=[],
                error="Failed to get page URL",
            )

    async def _extract_visible_text(self) -> str:
        text = ""
        for selector in CONTENT_SELECTORS:
            try:
                element = await self.page.query_selector(selector)
                if element and await element.is_visible():
                    text = (await element.inner_text()).strip()
                    if text:
                        break
            except Exception:
                continue

        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        return text

    async def _extract_interactive_elements(self) -> list[InteractiveElement]:
        all_handles = await self.page.query_selector_all(INTERACTIVE_SELECTORS)
        result: list[InteractiveElement] = []
        visible_handles: list[ElementHandle] = []

        for handle in all_handles:
            try:
                if not await handle.is_visible():
                    continue

                tag = (await (await handle.get_property("tagName")).json_value()).lower()
                role = await handle.get_attribute("role") or tag
                name = (
                    await handle.get_attribute("aria-label")
                    or (await handle.inner_text()).strip()
                    or await handle.get_attribute("placeholder")
                    or await handle.get_attribute("name")
                    or ""
                )
                name = name[:80]

                el_type = (
                    await handle.get_attribute("type")
                    if tag in ("input", "button")
                    else None
                )

                value = (
                    await handle.input_value(timeout=self._settings.PAGE_TIMEOUT)
                    if tag in ("input", "textarea")
                    else None
                )

                result.append(
                    InteractiveElement(
                        index=len(result),
                        tag=tag,
                        role=role,
                        name=name,
                        type=el_type,
                        value=value,
                        href=await handle.get_attribute("href") if tag == "a" else None,
                        placeholder=(
                            await handle.get_attribute("placeholder")
                            if tag in ("input", "textarea")
                            else None
                        ),
                    )
                )
                visible_handles.append(handle)
            except Exception:
                continue

        self._handles = visible_handles
        return result

    def _resolve_locator(self, selector: str):
        match = re.match(r"\[(\d+)]", selector)
        if not match:
            return self.page.locator(selector)

        idx = int(match.group(1))
        if idx >= len(self._handles):
            raise IndexError(
                f"Element index [{idx}] out of range (0-{len(self._handles) - 1})"
            )

        return self._handles[idx]

    async def _has_more_content(self) -> bool:
        threshold = self._settings.SCROLL_THRESHOLD
        return await self.page.evaluate(
            f"() => document.documentElement.scrollHeight > window.innerHeight + window.scrollY + {threshold}"
        )

    async def execute_action(self, action: AgentAction) -> ActionResult:
        try:
            action_type = ActionType(action.action)
            handler = getattr(self, action_type.handler)
            return await handler(action)
        except ValueError:
            return ActionResult(
                success=False,
                message=f"Unsupported action: {action.action}",
            )
        except Exception as e:
            return ActionResult(success=False, message="Action failed", error=str(e))

    async def _do_click(self, action: Click) -> ActionResult:
        locator = self._resolve_locator(action.selector)
        await locator.click(timeout=self._settings.PAGE_TIMEOUT)
        await self._wait_for_stable()
        return ActionResult(success=True, message=f"Clicked: {action.description}")

    async def _do_type(self, action: Type) -> ActionResult:
        locator = self._resolve_locator(action.selector)
        if action.clear_first:
            await locator.fill(action.text, timeout=self._settings.PAGE_TIMEOUT)
        else:
            await locator.press_sequentially(action.text, timeout=self._settings.PAGE_TIMEOUT)
        if action.press_enter:
            await locator.press("Enter")
            await self._wait_for_stable()
        return ActionResult(
            success=True, message=f"Typed '{action.text}': {action.description}"
        )

    async def _do_navigate(self, action: Navigate) -> ActionResult:
        await self.page.goto(action.url, timeout=30000, wait_until="domcontentloaded")
        return ActionResult(success=True, message=f"Navigated to {action.url}")

    async def _do_scroll(self, action: Scroll) -> ActionResult:
        delta = action.amount * 100
        if action.direction == "up":
            delta = -delta
        await self.page.evaluate(f"window.scrollBy(0, {delta})")
        return ActionResult(success=True, message=f"Scrolled {action.direction}")

    async def _do_wait(self, action: Wait) -> ActionResult:
        await asyncio.sleep(action.seconds)
        return ActionResult(success=True, message=f"Waited {action.seconds}s")

    async def _wait_for_stable(self) -> None:
        try:
            await self.page.wait_for_load_state("domcontentloaded", timeout=5000)
            await self.page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
        await asyncio.sleep(0.5)
