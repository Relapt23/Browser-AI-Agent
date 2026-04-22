from pydantic import BaseModel

from browser_agent.models.actions import AgentAction


class ActionResult(BaseModel):
    success: bool
    message: str
    error: str | None = None


class StepRecord(BaseModel):
    step: int
    action: AgentAction
    result: ActionResult
    page_url: str | None = None