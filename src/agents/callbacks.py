"""
Agent callback handlers
"""
import logging
from typing import Dict, Any
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.agents import AgentAction

logger = logging.getLogger(__name__)



class SimpleCallbackHandler(BaseCallbackHandler):
    """Basic callback handler for logging agent activity"""
    
    def __init__(self):
        pass
    
    async def on_tool_start(self, serialized, input_str, **kwargs):
        """Called when a tool starts execution"""
        tool_name = serialized.get('name', 'Unknown') if serialized else 'Unknown'
        logger.info(f"Starting tool: {tool_name}")
    
    async def on_tool_end(self, output: str, **kwargs):
        """Called when a tool finishes execution"""
        logger.info(f"Tool completed with output length: {len(output) if output else 0}")
    
    async def on_tool_error(self, error: Exception, **kwargs):
        """Called when a tool encounters an error"""
        logger.error(f"Tool error: {str(error)}")
    
    async def on_agent_action(self, action: AgentAction, **kwargs):
        """Called when agent decides to take an action"""
        logger.info(f"Agent action: {action.tool} - {action.log[:100]}...")
    
    async def on_llm_start(self, serialized: Dict[str, Any], prompts: list, **kwargs):
        """Called when LLM starts processing"""
        logger.info("LLM processing started")
    
    async def on_llm_end(self, response, **kwargs):
        """Called when LLM finishes processing"""
        logger.info("LLM processing completed")