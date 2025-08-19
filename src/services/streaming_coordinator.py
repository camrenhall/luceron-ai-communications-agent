"""
Real-time streaming coordinator for agent workflow events
"""
import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional, AsyncGenerator
from contextlib import asynccontextmanager

from src.models.streaming import (
    StreamEvent, StreamingState, WorkflowStartedEvent, 
    WorkflowCompletedEvent, WorkflowErrorEvent, HeartbeatEvent
)

logger = logging.getLogger(__name__)


class StreamingCoordinator:
    """Coordinates real-time streaming between workflow execution and SSE clients"""
    
    def __init__(self, max_queue_size: int = 1000, heartbeat_interval: int = 30):
        self.active_streams: Dict[str, asyncio.Queue] = {}
        self.streaming_states: Dict[str, StreamingState] = {}
        self.max_queue_size = max_queue_size
        self.heartbeat_interval = heartbeat_interval
        self._cleanup_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
    
    async def start(self):
        """Start background tasks"""
        self._cleanup_task = asyncio.create_task(self._cleanup_inactive_streams())
        self._heartbeat_task = asyncio.create_task(self._send_heartbeats())
        logger.info("StreamingCoordinator started")
    
    async def stop(self):
        """Stop background tasks and cleanup"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        
        # Close all active streams
        async with self._lock:
            for workflow_id in list(self.active_streams.keys()):
                await self._cleanup_stream(workflow_id)
        
        logger.info("StreamingCoordinator stopped")
    
    async def create_stream(self, workflow_id: str, initial_prompt: str) -> AsyncGenerator[StreamEvent, None]:
        """Create a new streaming session for a workflow"""
        async with self._lock:
            if workflow_id in self.active_streams:
                logger.warning(f"Stream already exists for workflow {workflow_id}")
                return
            
            # Create queue and state
            event_queue = asyncio.Queue(maxsize=self.max_queue_size)
            streaming_state = StreamingState(
                workflow_id=workflow_id,
                start_time=datetime.now(),
                last_activity=datetime.now()
            )
            
            self.active_streams[workflow_id] = event_queue
            self.streaming_states[workflow_id] = streaming_state
            
            logger.info(f"Created stream for workflow {workflow_id}")
        
        # Send initial event
        start_event = WorkflowStartedEvent(
            workflow_id=workflow_id,
            timestamp=datetime.now(),
            initial_prompt=initial_prompt
        )
        await self.emit_event(workflow_id, start_event)
        
        # Stream events from queue
        try:
            while True:
                try:
                    # Wait for event with timeout to allow cleanup checks
                    event = await asyncio.wait_for(
                        event_queue.get(), 
                        timeout=self.heartbeat_interval
                    )
                    
                    if event is None:  # Termination signal
                        break
                    
                    yield event
                    event_queue.task_done()
                    
                except asyncio.TimeoutError:
                    # Check if stream is still active
                    if workflow_id not in self.active_streams:
                        break
                    continue
                    
        except asyncio.CancelledError:
            logger.info(f"Stream cancelled for workflow {workflow_id}")
        except Exception as e:
            logger.error(f"Error in stream for workflow {workflow_id}: {e}")
            # Send error event
            error_event = WorkflowErrorEvent(
                workflow_id=workflow_id,
                timestamp=datetime.now(),
                error_message=str(e),
                error_type=type(e).__name__
            )
            await self.emit_event(workflow_id, error_event)
        finally:
            await self._cleanup_stream(workflow_id)
    
    async def emit_event(self, workflow_id: str, event: StreamEvent) -> bool:
        """Emit an event to the stream queue"""
        async with self._lock:
            if workflow_id not in self.active_streams:
                logger.warning(f"No active stream for workflow {workflow_id}")
                return False
            
            queue = self.active_streams[workflow_id]
            state = self.streaming_states.get(workflow_id)
            
            try:
                # Non-blocking put to avoid hanging
                queue.put_nowait(event)
                
                if state:
                    state.mark_activity()
                
                logger.debug(f"Emitted {event.type} event for workflow {workflow_id}")
                return True
                
            except asyncio.QueueFull:
                logger.error(f"Queue full for workflow {workflow_id}, dropping event")
                return False
    
    async def complete_workflow(self, workflow_id: str, final_response: str, 
                              execution_time_ms: int) -> None:
        """Mark workflow as completed and send completion event"""
        state = self.streaming_states.get(workflow_id)
        tools_used = state.tools_used if state else []
        total_steps = state.step_counter if state else 0
        
        completion_event = WorkflowCompletedEvent(
            workflow_id=workflow_id,
            timestamp=datetime.now(),
            final_response=final_response,
            total_steps=total_steps,
            execution_time_ms=execution_time_ms,
            tools_used=tools_used
        )
        
        await self.emit_event(workflow_id, completion_event)
        
        # Send termination signal after a brief delay
        await asyncio.sleep(0.1)
        await self._terminate_stream(workflow_id)
    
    async def error_workflow(self, workflow_id: str, error_message: str, 
                           error_type: str, partial_response: Optional[str] = None) -> None:
        """Mark workflow as failed and send error event"""
        error_event = WorkflowErrorEvent(
            workflow_id=workflow_id,
            timestamp=datetime.now(),
            error_message=error_message,
            error_type=error_type,
            partial_response=partial_response
        )
        
        await self.emit_event(workflow_id, error_event)
        
        # Send termination signal after a brief delay
        await asyncio.sleep(0.1)
        await self._terminate_stream(workflow_id)
    
    async def _terminate_stream(self, workflow_id: str) -> None:
        """Send termination signal to stream"""
        async with self._lock:
            if workflow_id in self.active_streams:
                queue = self.active_streams[workflow_id]
                try:
                    queue.put_nowait(None)  # Termination signal
                except asyncio.QueueFull:
                    pass  # Will be cleaned up anyway
    
    async def _cleanup_stream(self, workflow_id: str) -> None:
        """Clean up stream resources"""
        async with self._lock:
            self.active_streams.pop(workflow_id, None)
            state = self.streaming_states.pop(workflow_id, None)
            
            if state:
                state.is_active = False
            
            logger.info(f"Cleaned up stream for workflow {workflow_id}")
    
    async def _cleanup_inactive_streams(self) -> None:
        """Background task to cleanup inactive streams"""
        while True:
            try:
                await asyncio.sleep(300)  # Check every 5 minutes
                
                cutoff_time = datetime.now() - timedelta(hours=1)
                inactive_workflows = []
                
                async with self._lock:
                    for workflow_id, state in self.streaming_states.items():
                        if state.last_activity < cutoff_time:
                            inactive_workflows.append(workflow_id)
                
                # Cleanup inactive streams
                for workflow_id in inactive_workflows:
                    logger.info(f"Cleaning up inactive stream: {workflow_id}")
                    await self._cleanup_stream(workflow_id)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")
    
    async def _send_heartbeats(self) -> None:
        """Background task to send heartbeat events"""
        while True:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                
                active_workflows = list(self.active_streams.keys())
                
                for workflow_id in active_workflows:
                    heartbeat = HeartbeatEvent(
                        workflow_id=workflow_id,
                        timestamp=datetime.now()
                    )
                    await self.emit_event(workflow_id, heartbeat)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in heartbeat task: {e}")
    
    def get_active_stream_count(self) -> int:
        """Get number of active streams"""
        return len(self.active_streams)
    
    def is_stream_active(self, workflow_id: str) -> bool:
        """Check if stream is active"""
        return workflow_id in self.active_streams


# Global coordinator instance
_coordinator: Optional[StreamingCoordinator] = None


async def get_streaming_coordinator() -> StreamingCoordinator:
    """Get the global streaming coordinator instance"""
    global _coordinator
    if _coordinator is None:
        _coordinator = StreamingCoordinator()
        await _coordinator.start()
    return _coordinator


async def shutdown_streaming_coordinator():
    """Shutdown the global coordinator"""
    global _coordinator
    if _coordinator:
        await _coordinator.stop()
        _coordinator = None


@asynccontextmanager
async def streaming_session(workflow_id: str, initial_prompt: str):
    """Context manager for streaming sessions"""
    coordinator = await get_streaming_coordinator()
    
    try:
        async for event in coordinator.create_stream(workflow_id, initial_prompt):
            yield event
    finally:
        # Cleanup handled by coordinator
        pass