from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from browser_agent.browser.executor import (
    ActionExecutor,
    ActionValidator,
    SnapshotManager,
)
from browser_agent.config import BrowserSettings
from browser_agent.models import ActionResult, AgentAction, Snapshot


class BrowserManager:
    def __init__(self, settings: BrowserSettings) -> None:
        self._settings = settings
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._snapshot_mgr: SnapshotManager | None = None
        self._executor: ActionExecutor | None = None

    async def __aenter__(self):
        await self.launch()
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    async def launch(self) -> None:
        self._playwright = await async_playwright().start()

        if self._settings.CDP_URL:
            await self._launch_over_cdp()
        else:
            await self._launch_local()

        await self._install_init_scripts()
        self._init_executor()

    async def close(self) -> None:
        try:
            if self._snapshot_mgr:
                await self._snapshot_mgr.invalidate(cleanup_dom=True)
        finally:
            try:
                if self._settings.CDP_URL:
                    if self._page:
                        await self._page.close()
                else:
                    if self._browser:
                        await self._browser.close()
            finally:
                if self._playwright:
                    await self._playwright.stop()

        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None
        self._snapshot_mgr = None
        self._executor = None

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Browser not launched")
        return self._page

    async def get_snapshot(self) -> Snapshot:
        if self._snapshot_mgr is None:
            raise RuntimeError("Browser not launched")
        return await self._snapshot_mgr.take_snapshot()

    async def execute_action(self, action: AgentAction) -> ActionResult:
        if self._executor is None:
            raise RuntimeError("Browser not launched")
        return await self._executor.execute(action)

    async def _launch_over_cdp(self) -> None:
        assert self._playwright is not None

        self._browser = await self._playwright.chromium.connect_over_cdp(
            self._settings.CDP_URL,
        )

        if self._browser.contexts:
            self._context = self._browser.contexts[0]
        else:
            self._context = await self._browser.new_context()

        self._page = await self._context.new_page()

    async def _launch_local(self) -> None:
        assert self._playwright is not None

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

    async def _install_init_scripts(self) -> None:
        if self._context is None:
            raise RuntimeError("Browser context not initialized")

        await self._context.add_init_script(
            """
            document.addEventListener('click', event => {
                const target = event.target;
                if (!(target instanceof Element)) return;

                const anchor = target.closest('a');
                if (anchor) anchor.removeAttribute('target');
            }, true);
            """
        )

    def _init_executor(self) -> None:
        if self._page is None:
            raise RuntimeError("Page not initialized")

        self._snapshot_mgr = SnapshotManager(self._page, self._settings)
        validator = ActionValidator(self._snapshot_mgr)

        self._executor = ActionExecutor(
            self._page,
            self._snapshot_mgr,
            validator,
            self._settings,
        )
