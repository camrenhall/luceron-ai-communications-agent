"""
Backend API integration service
"""
from src.config.settings import BACKEND_URL
from src.models.workflow import WorkflowState, WorkflowStatus, ReasoningStep
from src.services.http_client import get_http_client


async def create_workflow_state(state: WorkflowState) -> str:
    """Create workflow state in backend and return the generated workflow_id"""
    workflow_data = {
        "agent_type": state.agent_type,
        "case_id": state.case_id,
        "status": state.status.value,
        "initial_prompt": state.initial_prompt
    }
    
    http_client = get_http_client()
    response = await http_client.post(f"{BACKEND_URL}/api/workflows", json=workflow_data)
    response.raise_for_status()
    result = response.json()
    return result["workflow_id"]


async def update_workflow_status(workflow_id: str, status: WorkflowStatus) -> None:
    """Update workflow status in backend"""
    http_client = get_http_client()
    response = await http_client.put(
        f"{BACKEND_URL}/api/workflows/{workflow_id}/status",
        json={"status": status.value}
    )
    response.raise_for_status()


async def add_reasoning_step(workflow_id: str, step: ReasoningStep) -> None:
    """Add a reasoning step to the workflow"""
    step_data = step.model_dump()
    if 'timestamp' in step_data:
        step_data['timestamp'] = step_data['timestamp'].isoformat()
    
    http_client = get_http_client()
    response = await http_client.post(
        f"{BACKEND_URL}/api/workflows/{workflow_id}/reasoning-step",
        json=step_data
    )
    response.raise_for_status()
