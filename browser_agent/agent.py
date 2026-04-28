from browser_agent.browser import BrowserManager, SensitiveDetector
from browser_agent.browser.llm import LLMClient
from browser_agent.config import BrowserSettings, LLMSettings
from browser_agent.logger import console as log
from browser_agent.models import (
    ActionResult,
    AgentAction,
    AskUser,
    Done,
    SensitiveCheck,
    Snapshot,
    StepRecord,
)


class Agent:
    def __init__(
        self,
        browser_settings: BrowserSettings,
        llm_settings: LLMSettings,
    ) -> None:
        self._browser = BrowserManager(browser_settings)
        self._llm = LLMClient(llm_settings)
        self._max_steps = browser_settings.MAX_STEPS
        self._history: list[StepRecord] = []
        self._consecutive_failures = 0
        self._max_failures = 5

    async def run(self, task: str) -> None:
        log.show_task_start(task)

        async with self._browser:
            for step in range(1, self._max_steps + 1):
                snapshot = await self._browser.get_snapshot()

                if SensitiveDetector.check_captcha(snapshot):
                    log.show_warning(
                        "Captcha detected. Please solve it in the browser."
                    )
                    log.ask_input("Press Enter after solving the captcha")
                    continue

                if self._check_sensitive(SensitiveDetector.check_page(snapshot)):
                    return

                action = await self._llm.get_next_action(
                    task,
                    snapshot,
                    self._history,
                    step,
                )
                log.show_step(step, self._max_steps, action, snapshot.state.url)

                if isinstance(action, Done):
                    log.show_done(action.summary, action.success)
                    log.ask_input("Press Enter to close the browser")
                    return

                result = await self._handle_action(action, snapshot)
                if result is None:
                    return

                self._record_step(step, action, result, snapshot)

            log.show_warning(f"Step limit reached ({self._max_steps})")
            log.show_done("Task not completed — step limit reached", success=False)

    async def _handle_action(
        self,
        action: AgentAction,
        snapshot: Snapshot,
    ) -> ActionResult | None:
        if isinstance(action, AskUser):
            answer = log.ask_input(action.question)
            result = ActionResult(
                success=True,
                message=f"User answered: {answer}",
            )
            log.show_result(result)
            self._consecutive_failures = 0
            return result

        if self._check_sensitive(SensitiveDetector.check_action(action, snapshot)):
            return None

        result = await self._browser.execute_action(action)
        log.show_result(result)

        self._update_failure_counter(result)

        if self._consecutive_failures >= self._max_failures:
            log.show_done("Too many consecutive failures", success=False)
            return None

        return result

    def _update_failure_counter(self, result: ActionResult) -> None:
        if result.success:
            self._consecutive_failures = 0
        else:
            self._consecutive_failures += 1

    @staticmethod
    def _check_sensitive(check: SensitiveCheck) -> bool:
        if check.is_sensitive and not log.ask_confirmation(check.reason):
            log.show_done("Stopped by user", success=False)
            return True

        return False

    def _record_step(
        self,
        step: int,
        action: AgentAction,
        result: ActionResult,
        snapshot: Snapshot,
    ) -> None:
        self._history.append(
            StepRecord(
                step=step,
                action=action,
                result=result,
                page_url=snapshot.state.url,
                snapshot_id=getattr(action, "snapshot_id", None),
            )
        )
