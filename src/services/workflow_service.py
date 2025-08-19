"""
Workflow execution service
"""
import logging
import time
from typing import Optional

from src.models.workflow import WorkflowStatus
from src.services.backend_api import update_workflow_status, update_workflow
from src.services.streaming_coordinator import get_streaming_coordinator
from src.agents.communications import create_communications_agent
from src.agents.callbacks import WorkflowCallbackHandler, StreamingWorkflowCallbackHandler

logger = logging.getLogger(__name__)


async def execute_workflow(workflow_id: str, initial_prompt: str) -> None:
    """Execute a workflow and update status to completed when done (legacy version)"""
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
        final_response = _extract_agent_response(result)
            
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


async def execute_workflow_with_streaming(workflow_id: str, initial_prompt: str) -> str:
    """Execute a workflow with real-time streaming support and return the final response"""
    start_time = time.time()
    coordinator = await get_streaming_coordinator()
    
    try:
        # Update status to processing
        await update_workflow_status(workflow_id, WorkflowStatus.PROCESSING)
        
        # Execute agent with streaming callback handler
        callback_handler = StreamingWorkflowCallbackHandler(workflow_id)
        agent = create_communications_agent()
        
        logger.info(f"Starting workflow execution for {workflow_id}")
        
        result = await agent.ainvoke(
            {"input": initial_prompt},
            config={"callbacks": [callback_handler]}
        )
        
        # Extract the final response from the agent's output
        final_response = _extract_agent_response(result)
        
        # Calculate execution time
        execution_time_ms = int((time.time() - start_time) * 1000)
        
        logger.info(f"Workflow {workflow_id} completed with response length: {len(final_response)} in {execution_time_ms}ms")
        
        # Update workflow with final response and completed status
        await update_workflow(
            workflow_id, 
            status=WorkflowStatus.COMPLETED,
            final_response=final_response
        )
        
        # Notify streaming coordinator of completion
        await coordinator.complete_workflow(
            workflow_id, 
            final_response, 
            execution_time_ms
        )
        
        logger.info(f"Workflow {workflow_id} final response persisted to backend")
        
        return final_response
        
    except Exception as e:
        logger.error(f"Workflow {workflow_id} execution failed: {e}")
        
        # Update status to failed
        await update_workflow_status(workflow_id, WorkflowStatus.FAILED)
        
        # Extract user-friendly error message and recovery suggestion
        error_message = str(e)
        recovery_suggestion = None
        
        # Handle specific error types
        if isinstance(e, dict) and e.get('type') == 'error':
            error_data = e.get('error', {})
            error_type = error_data.get('type', 'unknown_error')
            error_message = error_data.get('message', str(e))
            
            if error_type == 'overloaded_error':
                error_message = "The AI service is currently overloaded"
                recovery_suggestion = "Please try again in a few moments"
        elif "overloaded" in str(e).lower():
            error_message = "The AI service is currently overloaded"
            recovery_suggestion = "Please try again in a few moments"
        elif "timeout" in str(e).lower():
            error_message = "Request timed out"
            recovery_suggestion = "Please try again"
        
        # Notify streaming coordinator of error with enhanced details
        await coordinator.error_workflow(
            workflow_id,
            error_message,
            type(e).__name__ if not isinstance(e, dict) else "APIError",
            recovery_suggestion
        )
        
        raise


def _extract_agent_response(result) -> str:
    """Extract the final response from agent output"""
    if not result:
        return ""
    
    agent_output = result.get("output", "") if result else ""
    
    # Handle case where output is an array of message objects
    if isinstance(agent_output, list) and len(agent_output) > 0:
        # Extract text from the first message object
        first_message = agent_output[0]
        if isinstance(first_message, dict) and "text" in first_message:
            return first_message["text"]
        else:
            return str(agent_output)
    else:
        # Output is already a string or empty
        return str(agent_output) if agent_output else ""