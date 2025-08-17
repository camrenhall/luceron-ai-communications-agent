"""
Backend API integration service
"""
from typing import Optional

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


async def update_workflow(workflow_id: str, status: Optional[WorkflowStatus] = None, 
                         final_response: Optional[str] = None) -> None:
    """Update workflow with status and/or final_response using the new PUT endpoint"""
    update_data = {}
    if status is not None:
        update_data["status"] = status.value
    if final_response is not None:
        update_data["final_response"] = final_response
    
    if not update_data:
        return
    
    http_client = get_http_client()
    response = await http_client.put(
        f"{BACKEND_URL}/api/workflows/{workflow_id}",
        json=update_data
    )
    response.raise_for_status()
