"""
Workflow execution service
"""
import logging

from src.models.workflow import WorkflowStatus
from src.services.backend_api import update_workflow_status
from src.agents.communications import create_communications_agent

logger = logging.getLogger(__name__)


async def execute_workflow(workflow_id: str, initial_prompt: str) -> None:
    """Execute a workflow and update status to completed when done"""
    try:
        # Update status to processing
        await update_workflow_status(workflow_id, WorkflowStatus.PROCESSING)
        
        # Execute agent
        agent = create_communications_agent()
        await agent.ainvoke({"input": initial_prompt})
        
        # Update status to completed
        await update_workflow_status(workflow_id, WorkflowStatus.COMPLETED)
        
    except Exception as e:
        logger.error(f"Workflow {workflow_id} execution failed: {e}")
        # Update status to failed
        await update_workflow_status(workflow_id, WorkflowStatus.FAILED)
        raise