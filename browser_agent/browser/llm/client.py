import json
import re

from openai import AsyncOpenAI
from pydantic import TypeAdapter

from browser_agent.browser.llm.prompts import (
    get_system_prompt,
    format_history,
    format_page_state,
)
from browser_agent.config import LLMSettings
from browser_agent.models import AgentAction, Done, PageState, StepRecord


class LLMClient:
    def __init__(self, settings: LLMSettings) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.API_KEY,
            base_url=settings.BASE_URL,
            max_retries=3,
        )
        self._model = settings.MODEL
        self._system_prompt = get_system_prompt()
        self._action_adapter = TypeAdapter(AgentAction)
        self._supports_json_format = True

    async def get_next_action(
        self,
        task: str,
        page_state: PageState,
        history: list[StepRecord],
        step: int,
    ) -> AgentAction:
        messages = [
            {"role": "system", "content": self._system_prompt},
            {
                "role": "user",
                "content": self._build_user_message(task, page_state, history, step),
            },
        ]

        try:
            kwargs = {
                "model": self._model,
                "messages": messages,
                "temperature": 0.2,
            }
            if self._supports_json_format:
                kwargs["response_format"] = {"type": "json_object"}

            response = await self._client.chat.completions.create(**kwargs)
            raw = response.choices[0].message.content
            data = json.loads(self._extract_json(raw))

            return self._action_adapter.validate_python(data)
        except Exception as e:
            if "response_format" in str(e) or "json" in str(e).lower():
                self._supports_json_format = False

                return await self.get_next_action(task, page_state, history, step)

            return Done(summary=f"Не удалось получить ответ от LLM: {e}", success=False)

    @staticmethod
    def _extract_json(text: str) -> str:
        match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
        if match:
            return match.group(1).strip()

        match = re.search(r"\{.*}", text, re.DOTALL)
        if match:
            return match.group(0)

        return text

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
