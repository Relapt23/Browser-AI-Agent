from openai import AsyncOpenAI

from browser_agent.browser.llm.prompts import (
    get_system_prompt,
    format_history,
    format_page_state,
)
from browser_agent.config import LLMSettings
from browser_agent.models import AgentAction, Done, LLMResponse, PageState, StepRecord


class LLMClient:
    def __init__(self, settings: LLMSettings) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.API_KEY,
            base_url=settings.BASE_URL,
            max_retries=3,
        )
        self._model = settings.MODEL

    async def get_next_action(
        self,
        task: str,
        page_state: PageState,
        history: list[StepRecord],
        step: int,
    ) -> AgentAction:
        messages = [
            {"role": "system", "content": get_system_prompt()},
            {
                "role": "user",
                "content": self._build_user_message(task, page_state, history, step),
            },
        ]

        try:
            response = await self._client.beta.chat.completions.parse(
                model=self._model,
                messages=messages,
                response_format=LLMResponse,
                temperature=0.2,
            )

            parsed = response.choices[0].message.parsed
            if parsed is None:
                return Done(summary="LLM вернул невалидный ответ", success=False)

            return parsed.action
        except Exception:
            return Done(summary="Не удалось получить ответ от LLM", success=False)

    @staticmethod
    def _build_user_message(
        task: str,
        page_state: PageState,
        history: list[StepRecord],
        step: int,
    ) -> str:
        parts = [
            f"Задача: {task}",
            f"Шаг: {step}",
            format_page_state(page_state),
        ]

        history_text = format_history(history)
        if history_text:
            parts.append(history_text)

        return "\n\n".join(parts)
