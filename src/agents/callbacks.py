"""
Agent callback handlers
"""
from datetime import datetime
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.agents import AgentAction

from src.models.workflow import ReasoningStep
from src.services.backend_api import add_reasoning_step


class WorkflowCallbackHandler(BaseCallbackHandler):
    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id
    
    async def on_tool_start(self, serialized, input_str, **kwargs):
        tool_name = serialized.get('name', 'Unknown')
        await add_reasoning_step(self.workflow_id, ReasoningStep(
            timestamp=datetime.now(),
            thought=f"Executing {tool_name}",
            action=tool_name
        ))
    
    async def on_agent_action(self, action: AgentAction, **kwargs):
        await add_reasoning_step(self.workflow_id, ReasoningStep(
            timestamp=datetime.now(),
            thought=f"Agent using {action.tool}: {action.log[:100]}..."
        ))