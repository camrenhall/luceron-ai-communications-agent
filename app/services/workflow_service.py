"""
Workflow execution service
"""
import logging

from app.config.settings import BACKEND_URL
from app.models.workflow import WorkflowStatus
from app.services.http_client import get_http_client
from app.services.backend_api import update_workflow_status
from app.agents.communications import create_communications_agent
from app.agents.callbacks import WorkflowCallbackHandler

logger = logging.getLogger(__name__)


async def execute_workflow(workflow_id: str) -> None:
    """Execute a workflow by ID"""
    # Load workflow state
    http_client = get_http_client()
    response = await http_client.get(f"{BACKEND_URL}/api/workflows/{workflow_id}")
    response.raise_for_status()
    data = response.json()
    
    # Update to processing
    await update_workflow_status(workflow_id, WorkflowStatus.PROCESSING)
    
    try:
        # Execute agent
        callback_handler = WorkflowCallbackHandler(workflow_id)
        agent = create_communications_agent(workflow_id)
        
        await agent.ainvoke(
            {"input": data["initial_prompt"]},
            config={"callbacks": [callback_handler]}
        )
        
        await update_workflow_status(workflow_id, WorkflowStatus.COMPLETED)
        
    except Exception as e:
        logger.error(f"Workflow {workflow_id} failed: {e}")
        await update_workflow_status(workflow_id, WorkflowStatus.FAILED)
        raise