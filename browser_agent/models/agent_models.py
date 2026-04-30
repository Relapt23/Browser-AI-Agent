from pydantic import BaseModel

from browser_agent.models.actions_models import AgentAction


class ActionResult(BaseModel):
    success: bool
    message: str
    error: str | None = None
    observation: str | None = None
    after_state: dict | None = None
    verification_passed: bool | None = None


class StepRecord(BaseModel):
    step: int
    action: AgentAction
    result: ActionResult
    page_url: str | None = None
    snapshot_id: str | None = None