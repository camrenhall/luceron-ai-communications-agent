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
        self.total_tokens: Optional[int] = None
        
    async def on_llm_start(self, serialized: Dict[str, Any], prompts: list, **kwargs):
        """Called when LLM starts processing"""
        logger.info("🧠 LLM processing started - analyzing user input and determining appropriate tools to use")
    
    async def on_llm_end(self, response, **kwargs):
        """Called when LLM finishes processing"""
        logger.info("✅ LLM processing completed")
        
        # Extract token usage if available for potential use in final response
        self.total_tokens = None
        if hasattr(response, 'llm_output') and response.llm_output:
            token_usage = response.llm_output.get('token_usage', {})
            self.total_tokens = token_usage.get('total_tokens')
        
    
    async def on_agent_action(self, action: AgentAction, **kwargs):
        """Called when agent decides to take an action"""
        logger.info(f"🎯 Agent action planned: {action.tool}")
        logger.debug(f"Agent reasoning: {action.log[:200]}...")
        
        self.current_reasoning = action.log
    
    async def on_tool_start(self, serialized, input_str, **kwargs):
        """Called when a tool starts execution"""
        tool_name = serialized.get('name', 'Unknown') if serialized else 'Unknown'
        logger.info(f"🛠️ Executing tool: {tool_name}")
        logger.debug(f"Tool input: {str(input_str)[:200]}...")
        
        self.active_tools[tool_name] = {
            "start_time": time.time(),
            "input": input_str,
            "name": tool_name
        }
    
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
        
        logger.info(f"✅ Tool completed: {tool_name} (output length: {len(output) if output else 0}, time: {execution_time_ms}ms)")
        logger.debug(f"Tool output preview: {output[:200] if output else 'No output'}...")
    
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
        
        logger.error(f"❌ Tool error: {tool_name} - {str(error)} (time: {execution_time_ms}ms)")
    
    async def store_final_response(self, final_response: str):
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
                    total_tokens=self.total_tokens
                )
                logger.info(f"📝 Stored final response in conversation {self.conversation_id}")
            except Exception as e:
                logger.error(f"❌ Failed to store final response: {e}")
    
