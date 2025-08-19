"""
Agent callback handlers
"""
import uuid
import time
from datetime import datetime
from typing import Optional, Dict, Any
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.agents import AgentAction

from src.models.workflow import ReasoningStep
from src.models.streaming import (
    ReasoningStepEvent, ToolStartEvent, ToolEndEvent, 
    AgentThinkingEvent, StreamingState
)
from src.services.backend_api import add_reasoning_step
from src.services.streaming_coordinator import get_streaming_coordinator


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


class StreamingWorkflowCallbackHandler(BaseCallbackHandler):
    """Enhanced callback handler that provides real-time streaming of agent events"""
    
    def __init__(self, workflow_id: str, enable_backend_persistence: bool = True):
        self.workflow_id = workflow_id
        self.enable_backend_persistence = enable_backend_persistence
        self.step_counter = 0
        self.active_tools: Dict[str, float] = {}  # tool_name -> start_time
        self._coordinator: Optional[Any] = None
    
    async def _get_coordinator(self):
        """Lazy initialization of streaming coordinator"""
        if self._coordinator is None:
            self._coordinator = await get_streaming_coordinator()
        return self._coordinator
    
    async def on_agent_action(self, action: AgentAction, **kwargs):
        """Called when agent decides to take an action"""
        coordinator = await self._get_coordinator()
        
        # Increment step counter
        self.step_counter += 1
        
        # Create reasoning step event
        step_event = ReasoningStepEvent(
            workflow_id=self.workflow_id,
            timestamp=datetime.now(),
            step_id=str(uuid.uuid4()),
            thought=action.log,
            action=action.tool,
            action_input=action.tool_input,
            step_number=self.step_counter
        )
        
        # Stream to frontend
        await coordinator.emit_event(self.workflow_id, step_event)
        
        # Persist to backend if enabled
        if self.enable_backend_persistence:
            await add_reasoning_step(self.workflow_id, ReasoningStep(
                timestamp=datetime.now(),
                thought=action.log,
                action=action.tool,
                action_input=action.tool_input
            ))
    
    async def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs):
        """Called when a tool starts execution"""
        coordinator = await self._get_coordinator()
        tool_name = serialized.get('name', 'Unknown')
        
        # Track tool start time
        self.active_tools[tool_name] = time.time()
        
        # Parse tool input
        tool_input = {}
        try:
            if isinstance(input_str, str):
                # Simple string input
                tool_input = {"input": input_str}
            elif isinstance(input_str, dict):
                tool_input = input_str
        except Exception:
            tool_input = {"input": str(input_str)}
        
        # Create tool start event
        tool_start_event = ToolStartEvent(
            workflow_id=self.workflow_id,
            timestamp=datetime.now(),
            tool_name=tool_name,
            tool_input=tool_input,
            description=serialized.get('description')
        )
        
        # Stream to frontend
        await coordinator.emit_event(self.workflow_id, tool_start_event)
        
        # Update streaming state
        state = coordinator.streaming_states.get(self.workflow_id)
        if state:
            state.add_tool(tool_name)
        
        # Persist to backend if enabled
        if self.enable_backend_persistence:
            await add_reasoning_step(self.workflow_id, ReasoningStep(
                timestamp=datetime.now(),
                thought=f"Starting tool: {tool_name}",
                action=tool_name,
                action_input=tool_input
            ))
    
    async def on_tool_end(self, output: str, **kwargs):
        """Called when a tool finishes execution"""
        coordinator = await self._get_coordinator()
        
        # Find the most recently started tool (simple heuristic)
        if self.active_tools:
            tool_name = max(self.active_tools.keys(), key=lambda x: self.active_tools[x])
            start_time = self.active_tools.pop(tool_name)
            execution_time_ms = int((time.time() - start_time) * 1000)
        else:
            tool_name = "Unknown"
            execution_time_ms = None
        
        # Create tool end event
        tool_end_event = ToolEndEvent(
            workflow_id=self.workflow_id,
            timestamp=datetime.now(),
            tool_name=tool_name,
            tool_output=output[:500] if output else None,  # Limit output size
            success=True,
            execution_time_ms=execution_time_ms
        )
        
        # Stream to frontend
        await coordinator.emit_event(self.workflow_id, tool_end_event)
        
        # Persist to backend if enabled
        if self.enable_backend_persistence:
            await add_reasoning_step(self.workflow_id, ReasoningStep(
                timestamp=datetime.now(),
                thought=f"Completed tool: {tool_name}",
                action=tool_name,
                action_output=output[:200] if output else None
            ))
    
    async def on_tool_error(self, error: Exception, **kwargs):
        """Called when a tool encounters an error"""
        coordinator = await self._get_coordinator()
        
        # Find the tool that errored
        if self.active_tools:
            tool_name = max(self.active_tools.keys(), key=lambda x: self.active_tools[x])
            start_time = self.active_tools.pop(tool_name)
            execution_time_ms = int((time.time() - start_time) * 1000)
        else:
            tool_name = "Unknown"
            execution_time_ms = None
        
        # Create tool error event
        tool_end_event = ToolEndEvent(
            workflow_id=self.workflow_id,
            timestamp=datetime.now(),
            tool_name=tool_name,
            tool_output=None,
            success=False,
            error_message=str(error),
            execution_time_ms=execution_time_ms
        )
        
        # Stream to frontend
        await coordinator.emit_event(self.workflow_id, tool_end_event)
    
    async def on_llm_start(self, serialized: Dict[str, Any], prompts: list, **kwargs):
        """Called when LLM starts processing"""
        coordinator = await self._get_coordinator()
        
        # Create agent thinking event
        thinking_event = AgentThinkingEvent(
            workflow_id=self.workflow_id,
            timestamp=datetime.now(),
            thinking="Analyzing prompt and planning response...",
            planning_stage="analysis"
        )
        
        # Stream to frontend
        await coordinator.emit_event(self.workflow_id, thinking_event)
    
    async def on_llm_end(self, response, **kwargs):
        """Called when LLM finishes processing"""
        coordinator = await self._get_coordinator()
        
        # Extract response content
        response_text = ""
        if hasattr(response, 'generations') and response.generations:
            if hasattr(response.generations[0][0], 'text'):
                response_text = response.generations[0][0].text
        
        # Create agent thinking event
        thinking_event = AgentThinkingEvent(
            workflow_id=self.workflow_id,
            timestamp=datetime.now(),
            thinking=f"Generated response: {response_text[:100]}..." if response_text else "Response generated",
            planning_stage="execution"
        )
        
        # Stream to frontend
        await coordinator.emit_event(self.workflow_id, thinking_event)
    
    async def on_chain_start(self, serialized: Dict[str, Any], inputs: Dict[str, Any], **kwargs):
        """Called when a chain starts"""
        coordinator = await self._get_coordinator()
        
        chain_name = serialized.get('name', 'Unknown Chain')
        
        # Create agent thinking event
        thinking_event = AgentThinkingEvent(
            workflow_id=self.workflow_id,
            timestamp=datetime.now(),
            thinking=f"Starting chain: {chain_name}",
            planning_stage="planning"
        )
        
        # Stream to frontend
        await coordinator.emit_event(self.workflow_id, thinking_event)
    
    def get_step_count(self) -> int:
        """Get current step count"""
        return self.step_counter