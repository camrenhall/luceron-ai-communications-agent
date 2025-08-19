"""
Agent callback handlers for conversation tracking
"""
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.agents import AgentAction

from src.services.backend_api import add_message
from src.models.agent_state import MessageRole

logger = logging.getLogger(__name__)


class ConversationCallbackHandler(BaseCallbackHandler):
    """Callback handler that tracks agent interactions in conversations"""
    
    def __init__(self, conversation_id: str, track_to_backend: bool = True):
        self.conversation_id = conversation_id
        self.track_to_backend = track_to_backend
        self.active_tools: Dict[str, Dict[str, Any]] = {}  # tool tracking
        self.current_reasoning: Optional[str] = None
        
    async def on_llm_start(self, serialized: Dict[str, Any], prompts: list, **kwargs):
        """Called when LLM starts processing"""
        logger.info("🧠 LLM processing started")
        
        if self.track_to_backend and prompts:
            # Store the reasoning/thinking phase
            try:
                await add_message(
                    conversation_id=self.conversation_id,
                    role=MessageRole.ASSISTANT,
                    content={
                        "text": "Processing request and planning actions...",
                        "thinking": "Analyzing user input and determining appropriate tools to use",
                        "stage": "reasoning"
                    },
                    model_used="claude-3-5-sonnet-20241022"
                )
            except Exception as e:
                logger.error(f"❌ Failed to store LLM start message: {e}")
    
    async def on_llm_end(self, response, **kwargs):
        """Called when LLM finishes processing"""
        logger.info("✅ LLM processing completed")
        
        # Extract token usage if available
        total_tokens = None
        if hasattr(response, 'llm_output') and response.llm_output:
            token_usage = response.llm_output.get('token_usage', {})
            total_tokens = token_usage.get('total_tokens')
        
        # Store LLM completion (this will be overridden by agent final response)
        if self.track_to_backend:
            try:
                response_text = ""
                if hasattr(response, 'generations') and response.generations:
                    if hasattr(response.generations[0][0], 'text'):
                        response_text = response.generations[0][0].text[:200] + "..."
                
                await add_message(
                    conversation_id=self.conversation_id,
                    role=MessageRole.ASSISTANT,
                    content={
                        "text": response_text if response_text else "Generated response",
                        "stage": "completion"
                    },
                    model_used="claude-3-5-sonnet-20241022",
                    total_tokens=total_tokens
                )
            except Exception as e:
                logger.error(f"❌ Failed to store LLM end message: {e}")
    
    async def on_agent_action(self, action: AgentAction, **kwargs):
        """Called when agent decides to take an action"""
        logger.info(f"🎯 Agent action: {action.tool} - {action.log[:100]}...")
        
        # Store the reasoning behind this action
        self.current_reasoning = action.log
        
        if self.track_to_backend:
            try:
                await add_message(
                    conversation_id=self.conversation_id,
                    role=MessageRole.ASSISTANT,
                    content={
                        "text": f"I need to use {action.tool} to help with this request.",
                        "reasoning": action.log,
                        "planned_action": action.tool,
                        "stage": "planning"
                    },
                    model_used="claude-3-5-sonnet-20241022"
                )
            except Exception as e:
                logger.error(f"❌ Failed to store agent action message: {e}")
    
    async def on_tool_start(self, serialized, input_str, **kwargs):
        """Called when a tool starts execution"""
        tool_name = serialized.get('name', 'Unknown') if serialized else 'Unknown'
        logger.info(f"🛠️ Starting tool: {tool_name}")
        
        # Track tool start time and details
        self.active_tools[tool_name] = {
            "start_time": time.time(),
            "input": input_str,
            "name": tool_name
        }
        
        if self.track_to_backend:
            try:
                # Parse tool input safely
                tool_input = {}
                if isinstance(input_str, str):
                    tool_input = {"input": input_str}
                elif isinstance(input_str, dict):
                    tool_input = input_str
                else:
                    tool_input = {"input": str(input_str)}
                
                await add_message(
                    conversation_id=self.conversation_id,
                    role=MessageRole.ASSISTANT,
                    content={
                        "text": f"Executing {tool_name}...",
                        "reasoning": self.current_reasoning or f"Using {tool_name} to process request",
                        "stage": "execution"
                    },
                    function_name=tool_name,
                    function_arguments=tool_input,
                    model_used="claude-3-5-sonnet-20241022"
                )
            except Exception as e:
                logger.error(f"❌ Failed to store tool start message: {e}")
    
    async def on_tool_end(self, output: str, **kwargs):
        """Called when a tool finishes execution"""
        # Find the most recent tool (simple heuristic)
        if self.active_tools:
            tool_name = max(self.active_tools.keys(), key=lambda x: self.active_tools[x]["start_time"])
            tool_info = self.active_tools.pop(tool_name)
            execution_time_ms = int((time.time() - tool_info["start_time"]) * 1000)
        else:
            tool_name = "Unknown"
            execution_time_ms = None
        
        logger.info(f"✅ Tool completed: {tool_name} (output length: {len(output) if output else 0})")
        
        if self.track_to_backend:
            try:
                # Truncate output for storage (keep it manageable)
                truncated_output = output[:1000] + "..." if output and len(output) > 1000 else output
                
                await add_message(
                    conversation_id=self.conversation_id,
                    role=MessageRole.FUNCTION,
                    content={
                        "text": f"Tool {tool_name} completed successfully",
                        "output_preview": truncated_output[:200] if truncated_output else None,
                        "execution_time_ms": execution_time_ms,
                        "output_length": len(output) if output else 0
                    },
                    function_name=tool_name,
                    function_response={"output": truncated_output, "success": True},
                    model_used="claude-3-5-sonnet-20241022"
                )
            except Exception as e:
                logger.error(f"❌ Failed to store tool end message: {e}")
    
    async def on_tool_error(self, error: Exception, **kwargs):
        """Called when a tool encounters an error"""
        # Find the tool that errored
        if self.active_tools:
            tool_name = max(self.active_tools.keys(), key=lambda x: self.active_tools[x]["start_time"])
            tool_info = self.active_tools.pop(tool_name)
            execution_time_ms = int((time.time() - tool_info["start_time"]) * 1000)
        else:
            tool_name = "Unknown"
            execution_time_ms = None
        
        logger.error(f"❌ Tool error: {tool_name} - {str(error)}")
        
        if self.track_to_backend:
            try:
                await add_message(
                    conversation_id=self.conversation_id,
                    role=MessageRole.FUNCTION,
                    content={
                        "text": f"Tool {tool_name} encountered an error",
                        "error_message": str(error),
                        "execution_time_ms": execution_time_ms
                    },
                    function_name=tool_name,
                    function_response={"error": str(error), "success": False},
                    model_used="claude-3-5-sonnet-20241022"
                )
            except Exception as e:
                logger.error(f"❌ Failed to store tool error message: {e}")
    
    async def store_final_response(self, final_response: str, total_tokens: Optional[int] = None):
        """Store the agent's final response to the user"""
        if self.track_to_backend:
            try:
                await add_message(
                    conversation_id=self.conversation_id,
                    role=MessageRole.ASSISTANT,
                    content={
                        "text": final_response,
                        "stage": "final_response",
                        "response_length": len(final_response)
                    },
                    model_used="claude-3-5-sonnet-20241022",
                    total_tokens=total_tokens
                )
                logger.info(f"📝 Stored final response in conversation {self.conversation_id}")
            except Exception as e:
                logger.error(f"❌ Failed to store final response: {e}")


# Legacy handler for backwards compatibility
class SimpleCallbackHandler(ConversationCallbackHandler):
    """Simple callback handler that logs but doesn't track to backend"""
    
    def __init__(self):
        super().__init__(conversation_id="", track_to_backend=False)
        logger.warning("⚠️ Using legacy SimpleCallbackHandler - consider upgrading to ConversationCallbackHandler")