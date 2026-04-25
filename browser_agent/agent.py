from browser_agent.browser import BrowserManager, SensitiveDetector
from browser_agent.browser.llm import LLMClient
from browser_agent.config import BrowserSettings, LLMSettings
from browser_agent.logger import console as log
from browser_agent.models import (
    ActionResult,
    AskUser,
    Done,
    SensitiveCheck,
    StepRecord,
)


class Agent:
    def __init__(
        self, browser_settings: BrowserSettings, llm_settings: LLMSettings
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
                page_state = await self._browser.get_page_state()

                if SensitiveDetector.check_captcha(page_state):
                    log.show_warning("Обнаружена капча. Пройдите её в браузере вручную.")
                    log.ask_input("Нажмите Enter после прохождения капчи")
                    continue

                if self._require_confirmation(SensitiveDetector.check_page(page_state)):
                    return

                action = await self._llm.get_next_action(
                    task,
                    page_state,
                    self._history,
                    step,
                )

                log.show_step(step, self._max_steps, action, page_state.url)

                if isinstance(action, Done):
                    log.show_done(action.summary, action.success)
                    log.ask_input("Нажмите Enter для закрытия браузера")
                    return

                if isinstance(action, AskUser):
                    answer = log.ask_input(action.question)
                    result = ActionResult(
                        success=True, message=f"Пользователь ответил: {answer}"
                    )
                else:
                    if self._require_confirmation(
                        SensitiveDetector.check_action(action, self._browser.elements)
                    ):
                        return

                    result = await self._browser.execute_action(action)
                    log.show_result(result)

                    if result.success:
                        self._consecutive_failures = 0
                    else:
                        self._consecutive_failures += 1
                        if self._consecutive_failures >= self._max_failures:
                            log.show_done("Слишком много ошибок подряд", success=False)
                            return

                self._history_record(step, action, result, page_state.url)

            log.show_warning(f"Достигнут лимит шагов ({self._max_steps})")
            log.show_done("Задача не завершена — достигнут лимит шагов", success=False)

    @staticmethod
    def _require_confirmation(check: SensitiveCheck) -> bool:
        if check.is_sensitive and not log.ask_confirmation(check.reason):
            log.show_done("Остановлено пользователем", success=False)
            return True
        return False

    def _history_record(
        self, step: int, action, result: ActionResult, url: str
    ) -> None:
        self._history.append(
            StepRecord(
                step=step,
                action=action,
                result=result,
                page_url=url,
            )
        )
