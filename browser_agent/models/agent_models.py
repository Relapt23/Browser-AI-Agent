from pydantic import BaseModel

from browser_agent.models.actions_models import AgentAction


class ActionResult(BaseModel):
    success: bool
    message: str
    error: str | None = None


class LLMResponse(BaseModel):
    action: AgentAction


class StepRecord(BaseModel):
    step: int
    action: AgentAction
    result: ActionResult
    page_url: str | None = None