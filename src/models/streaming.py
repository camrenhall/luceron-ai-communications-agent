"""
Enhanced streaming event models for real-time frontend communication
"""
from datetime import datetime
from typing import Dict, List, Optional, Union, Any
from enum import Enum
from pydantic import BaseModel


class StreamEventType(str, Enum):
    """Types of streaming events sent to frontend"""
    WORKFLOW_STARTED = "workflow_started"
    REASONING_STEP = "reasoning_step"
    TOOL_START = "tool_start"
    TOOL_END = "tool_end"
    AGENT_THINKING = "agent_thinking"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_ERROR = "workflow_error"
    HEARTBEAT = "heartbeat"


class BaseStreamEvent(BaseModel):
    """Base class for all streaming events"""
    type: StreamEventType
    workflow_id: str
    timestamp: datetime
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class WorkflowStartedEvent(BaseStreamEvent):
    """Event sent when workflow begins execution"""
    type: StreamEventType = StreamEventType.WORKFLOW_STARTED
    initial_prompt: str
    agent_type: str = "CommunicationsAgent"


class ReasoningStepEvent(BaseStreamEvent):
    """Event sent for each reasoning step during agent execution"""
    type: StreamEventType = StreamEventType.REASONING_STEP
    step_id: str
    thought: str
    action: Optional[str] = None
    action_input: Optional[Dict[str, Any]] = None
    step_number: int


class ToolStartEvent(BaseStreamEvent):
    """Event sent when agent starts using a tool"""
    type: StreamEventType = StreamEventType.TOOL_START
    tool_name: str
    tool_input: Dict[str, Any]
    description: Optional[str] = None


class ToolEndEvent(BaseStreamEvent):
    """Event sent when agent finishes using a tool"""
    type: StreamEventType = StreamEventType.TOOL_END
    tool_name: str
    tool_output: Optional[str] = None
    success: bool = True
    error_message: Optional[str] = None
    execution_time_ms: Optional[int] = None


class AgentThinkingEvent(BaseStreamEvent):
    """Event sent for agent's internal reasoning and planning"""
    type: StreamEventType = StreamEventType.AGENT_THINKING
    thinking: str
    planning_stage: str  # "analysis", "planning", "execution", "review"


class WorkflowCompletedEvent(BaseStreamEvent):
    """Event sent when workflow completes successfully"""
    type: StreamEventType = StreamEventType.WORKFLOW_COMPLETED
    final_response: str
    total_steps: int
    execution_time_ms: int
    tools_used: List[str]


class WorkflowErrorEvent(BaseStreamEvent):
    """Event sent when workflow encounters an error"""
    type: StreamEventType = StreamEventType.WORKFLOW_ERROR
    error_message: str
    error_type: str
    recovery_suggestion: Optional[str] = None
    partial_response: Optional[str] = None


class HeartbeatEvent(BaseStreamEvent):
    """Periodic event to maintain connection"""
    type: StreamEventType = StreamEventType.HEARTBEAT
    status: str = "processing"


# Union type for all possible stream events
StreamEvent = Union[
    WorkflowStartedEvent,
    ReasoningStepEvent,
    ToolStartEvent,
    ToolEndEvent,
    AgentThinkingEvent,
    WorkflowCompletedEvent,
    WorkflowErrorEvent,
    HeartbeatEvent
]


class StreamingState(BaseModel):
    """Manages state for real-time streaming coordination"""
    workflow_id: str
    is_active: bool = True
    start_time: datetime
    last_activity: datetime
    event_count: int = 0
    step_counter: int = 0
    tools_used: List[str] = []
    
    def increment_step(self) -> int:
        """Increment and return step counter"""
        self.step_counter += 1
        self.last_activity = datetime.now()
        return self.step_counter
    
    def add_tool(self, tool_name: str) -> None:
        """Track tool usage"""
        if tool_name not in self.tools_used:
            self.tools_used.append(tool_name)
    
    def mark_activity(self) -> None:
        """Update last activity timestamp"""
        self.last_activity = datetime.now()
        self.event_count += 1