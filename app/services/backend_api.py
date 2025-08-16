"""
Backend API integration service
"""
from app.config.settings import BACKEND_URL
from app.models.workflow import WorkflowState, WorkflowStatus, ReasoningStep
from app.services.http_client import get_http_client


async def create_workflow_state(state: WorkflowState) -> None:
    workflow_data = {
        "workflow_id": state.workflow_id,
        "agent_type": state.agent_type,
        "case_id": state.case_id,
        "status": state.status.value,
        "initial_prompt": state.initial_prompt
    }
    
    http_client = get_http_client()
    response = await http_client.post(f"{BACKEND_URL}/api/workflows", json=workflow_data)
    response.raise_for_status()


async def update_workflow_status(workflow_id: str, status: WorkflowStatus) -> None:
    http_client = get_http_client()
    response = await http_client.put(
        f"{BACKEND_URL}/api/workflows/{workflow_id}/status",
        json={"status": status.value}
    )
    response.raise_for_status()


async def add_reasoning_step(workflow_id: str, step: ReasoningStep) -> None:
    step_data = step.model_dump()
    if 'timestamp' in step_data:
        step_data['timestamp'] = step_data['timestamp'].isoformat()
    
    http_client = get_http_client()
    response = await http_client.post(
        f"{BACKEND_URL}/api/workflows/{workflow_id}/reasoning-step",
        json=step_data
    )
    response.raise_for_status()