"""
Workflow execution service
"""
import logging

from src.models.workflow import WorkflowStatus
from src.services.backend_api import update_workflow_status, update_workflow
from src.agents.communications import create_communications_agent
from src.agents.callbacks import WorkflowCallbackHandler

logger = logging.getLogger(__name__)


async def execute_workflow(workflow_id: str, initial_prompt: str) -> None:
    """Execute a workflow and update status to completed when done"""
    try:
        # Update status to processing
        await update_workflow_status(workflow_id, WorkflowStatus.PROCESSING)
        
        # Execute agent with callback handler for reasoning step tracking
        callback_handler = WorkflowCallbackHandler(workflow_id)
        agent = create_communications_agent()
        result = await agent.ainvoke(
            {"input": initial_prompt},
            config={"callbacks": [callback_handler]}
        )
        
        # Extract the final response from the agent's output
        agent_output = result.get("output", "") if result else ""
        
        # Handle case where output is an array of message objects
        if isinstance(agent_output, list) and len(agent_output) > 0:
            # Extract text from the first message object
            first_message = agent_output[0]
            if isinstance(first_message, dict) and "text" in first_message:
                final_response = first_message["text"]
            else:
                final_response = str(agent_output)
        else:
            # Output is already a string or empty
            final_response = str(agent_output) if agent_output else ""
            
        logger.info(f"Workflow {workflow_id} completed with response length: {len(final_response)}")
        
        # Update workflow with final response and completed status
        await update_workflow(
            workflow_id, 
            status=WorkflowStatus.COMPLETED,
            final_response=final_response
        )
        logger.info(f"Workflow {workflow_id} final response persisted to backend")
        
    except Exception as e:
        logger.error(f"Workflow {workflow_id} execution failed: {e}")
        # Update status to failed
        await update_workflow_status(workflow_id, WorkflowStatus.FAILED)
        raise