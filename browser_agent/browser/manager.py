import asyncio
import re

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

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
        handles = await self.page.query_selector_all(INTERACTIVE_SELECTORS)
        result: list[InteractiveElement] = []
        idx = 0

        for handle in handles:
            try:
                if not await handle.is_visible():
                    continue

                tag = (await handle.get_property("tagName")).lower()
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

                href = await handle.get_attribute("href") if tag == "a" else None
                placeholder = (
                    await handle.get_attribute("placeholder")
                    if tag in ("input", "textarea")
                    else None
                )

                selector = await self._build_selector(handle)

                result.append(
                    InteractiveElement(
                        index=idx,
                        tag=tag,
                        role=role,
                        name=name,
                        type=el_type,
                        value=value,
                        href=href,
                        placeholder=placeholder,
                        selector=selector,
                    )
                )
                idx += 1
            except Exception:
                continue

        return result

    async def _build_selector(self, handle) -> str:
        test_id = await handle.get_attribute("data-testid")
        if test_id:
            return f'[data-testid="{test_id}"]'

        el_id = await handle.get_attribute("id")
        if el_id:
            return f"#{el_id}"

        return await handle.evaluate("""e => {
            const parts = [];
            while (e && e.nodeType === Node.ELEMENT_NODE) {
                let selector = e.tagName.toLowerCase();
                if (e.id) {
                    parts.unshift('#' + e.id);
                    break;
                }
                const parent = e.parentElement;
                if (parent) {
                    const siblings = Array.from(parent.children).filter(
                        c => c.tagName === e.tagName
                    );
                    if (siblings.length > 1) {
                        const idx = siblings.indexOf(e) + 1;
                        selector += ':nth-of-type(' + idx + ')';
                    }
                }
                parts.unshift(selector);
                e = parent;
            }
            return parts.join(' > ');
        }""")

    async def _has_more_content(self) -> bool:
        return await self.page.evaluate(
            "() => document.documentElement.scrollHeight > window.innerHeight + window.scrollY + 100"
        )

    # ── Action execution ──

    async def execute_action(self, action: AgentAction) -> ActionResult:
        try:
            if isinstance(action, Click):
                return await self._do_click(action)
            elif isinstance(action, Type):
                return await self._do_type(action)
            elif isinstance(action, Navigate):
                return await self._do_navigate(action)
            elif isinstance(action, Scroll):
                return await self._do_scroll(action)
            elif isinstance(action, Wait):
                return await self._do_wait(action)
            else:
                return ActionResult(
                    success=False,
                    message=f"Unsupported action: {action.action}",
                )
        except Exception as e:
            return ActionResult(success=False, message="Action failed", error=str(e))

    def _resolve_selector(self, selector: str) -> str:
        match = re.match(r"\[(\d+)]", selector)
        if match:
            idx = int(match.group(1))
            if 0 <= idx < len(self._elements):
                return self._elements[idx].selector
            raise IndexError(
                f"Element index [{idx}] out of range (0-{len(self._elements) - 1})"
            )
        return selector

    async def _do_click(self, action: Click) -> ActionResult:
        selector = self._resolve_selector(action.selector)
        await self.page.click(selector, timeout=10000)
        await self._wait_for_stable()
        return ActionResult(success=True, message=f"Clicked: {action.description}")

    async def _do_type(self, action: Type) -> ActionResult:
        selector = self._resolve_selector(action.selector)
        if action.clear_first:
            await self.page.fill(selector, "", timeout=10000)
        await self.page.fill(selector, action.text, timeout=10000)
        if action.press_enter:
            await self.page.press(selector, "Enter")
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
        await asyncio.sleep(0.3)
        return ActionResult(success=True, message=f"Scrolled {action.direction}")

    async def _do_wait(self, action: Wait) -> ActionResult:
        await asyncio.sleep(action.seconds)
        return ActionResult(success=True, message=f"Waited {action.seconds}s")

    async def _wait_for_stable(self) -> None:
        try:
            await self.page.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception:
            pass
        await asyncio.sleep(0.3)
