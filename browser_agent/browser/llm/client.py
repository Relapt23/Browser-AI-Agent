import json
import re

from openai import AsyncOpenAI
from pydantic import TypeAdapter

from browser_agent.browser.llm.prompts import (
    get_system_prompt,
    format_history,
    format_snapshot,
)
from browser_agent.config import LLMSettings
from browser_agent.logger import console as log
from browser_agent.models import AgentAction, Done, Snapshot, StepRecord


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
        snapshot: Snapshot,
        history: list[StepRecord],
        step: int,
    ) -> AgentAction:
        user_message = self._build_user_message(task, snapshot, history, step)
        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": user_message},
        ]

        log.show_llm_request(user_message, step)

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
            log.show_llm_response(raw)
            data = json.loads(self._extract_json(raw))

            return self._action_adapter.validate_python(data)
        except Exception as e:
            if self._supports_json_format and (
                "response_format" in str(e) or "json" in str(e).lower()
            ):
                self._supports_json_format = False
                return await self.get_next_action(task, snapshot, history, step)

            return Done(summary=f"Failed to get LLM response: {e}", success=False)

    @staticmethod
    def _extract_json(text: str) -> str:
        match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
        if match:
            text = match.group(1).strip()

        start = text.find("{")
        if start == -1:
            return text

        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]

        return text

    @staticmethod
    def _build_user_message(
        task: str,
        snapshot: Snapshot,
        history: list[StepRecord],
        step: int,
    ) -> str:
        parts = [
            f"Task: {task}",
            f"Step: {step}",
            format_snapshot(snapshot),
        ]

        history_text = format_history(history)
        if history_text:
            parts.append(history_text)

        return "\n\n".join(parts)