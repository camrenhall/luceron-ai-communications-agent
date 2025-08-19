"""
Token Management Service

Handles intelligent token usage optimization through conversation summarization,
context compression, and adaptive context window management following the
patterns described in the Agent State Management guide.
"""
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

from src.services.backend_api import (
    get_message_count, create_auto_summary, get_latest_summary,
    get_conversation_history, add_message
)
from src.models.agent_state import MessageRole

logger = logging.getLogger(__name__)


class TokenManager:
    """Manages token usage optimization for agent conversations"""
    
    def __init__(self, max_context_messages: int = 20, summary_threshold: int = 15):
        self.max_context_messages = max_context_messages
        self.summary_threshold = summary_threshold
        
    async def optimize_conversation_context(
        self, 
        conversation_id: str,
        force_summary: bool = False
    ) -> Dict[str, Any]:
        """
        Optimize conversation context by creating summaries when needed
        
        Returns:
            Dictionary with optimization results and metrics
        """
        try:
            message_count = await get_message_count(conversation_id)
            optimization_result = {
                "conversation_id": conversation_id,
                "message_count": message_count,
                "action_taken": "none",
                "tokens_saved": 0,
                "summary_created": False
            }
            
            # Check if summarization is needed
            should_summarize = force_summary or message_count > self.max_context_messages
            
            if should_summarize:
                logger.info(f"🔄 Optimizing conversation {conversation_id} ({message_count} messages)")
                
                # Calculate how many messages to summarize
                messages_to_keep = min(10, message_count // 3)  # Keep recent 1/3 or 10 messages
                messages_to_summarize = max(self.summary_threshold, message_count - messages_to_keep)
                
                # Create summary
                summary_result = await create_auto_summary(
                    conversation_id, 
                    messages_to_summarize=messages_to_summarize
                )
                
                optimization_result.update({
                    "action_taken": "summarized",
                    "messages_summarized": messages_to_summarize,
                    "messages_kept": messages_to_keep,
                    "summary_created": True,
                    "summary_id": summary_result.get("summary_id"),
                    "tokens_saved": summary_result.get("tokens_saved", 0)
                })
                
                logger.info(f"📄 Created summary: {messages_to_summarize} messages → summary")
            
            return optimization_result
            
        except Exception as e:
            logger.error(f"Failed to optimize conversation context: {e}")
            return {
                "conversation_id": conversation_id,
                "action_taken": "error",
                "error": str(e)
            }
    
    async def prepare_context_for_agent(
        self,
        conversation_id: str,
        max_recent_messages: int = 10
    ) -> Dict[str, Any]:
        """Prepare optimized context for agent execution"""
        try:
            context_data = {
                "conversation_id": conversation_id,
                "context_type": "optimized",
                "prepared_at": datetime.now().isoformat()
            }
            
            # Get conversation summary if available
            try:
                latest_summary = await get_latest_summary(conversation_id)
                if latest_summary:
                    context_data["summary"] = {
                        "content": latest_summary["summary_content"],
                        "messages_summarized": latest_summary["messages_summarized"],
                        "created_at": latest_summary.get("created_at")
                    }
                    logger.info(f"📖 Using summary of {latest_summary['messages_summarized']} messages")
            except Exception as e:
                logger.debug(f"No summary available: {e}")
            
            # Get recent detailed messages
            try:
                recent_messages = await get_conversation_history(
                    conversation_id,
                    limit=max_recent_messages,
                    include_function_calls=True
                )
                
                if recent_messages:
                    context_data["recent_messages"] = [
                        {
                            "role": msg["role"],
                            "content": self._compress_message_content(msg["content"]),
                            "timestamp": msg.get("created_at"),
                            "has_function_call": bool(msg.get("function_name"))
                        }
                        for msg in recent_messages
                    ]
                    
                    logger.info(f"📋 Included {len(recent_messages)} recent messages")
            except Exception as e:
                logger.warning(f"Could not load recent messages: {e}")
            
            return context_data
            
        except Exception as e:
            logger.error(f"Failed to prepare agent context: {e}")
            return {"conversation_id": conversation_id, "context_type": "error"}
    
    def _compress_message_content(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """Compress message content to reduce token usage while preserving key information"""
        if not isinstance(content, dict):
            return {"text": str(content)[:200] + "..." if len(str(content)) > 200 else str(content)}
        
        compressed = {}
        
        # Keep essential text content, truncate if very long
        if "text" in content:
            text = content["text"]
            if len(text) > 300:
                compressed["text"] = text[:300] + "..."
            else:
                compressed["text"] = text
        
        # Preserve key metadata
        preserve_keys = ["stage", "message_type", "reasoning", "planned_action", 
                        "execution_time_ms", "success", "error_message"]
        
        for key in preserve_keys:
            if key in content:
                compressed[key] = content[key]
        
        # Truncate large nested objects
        for key, value in content.items():
            if key not in compressed and key not in ["text"]:
                if isinstance(value, (dict, list)) and len(str(value)) > 100:
                    compressed[key] = str(value)[:100] + "..."
                elif not isinstance(value, (dict, list)):
                    compressed[key] = value
        
        return compressed
    
    async def estimate_token_usage(
        self,
        conversation_id: str,
        include_context: bool = True
    ) -> Dict[str, Any]:
        """Estimate token usage for conversation context"""
        try:
            estimates = {
                "conversation_id": conversation_id,
                "estimation_method": "heuristic",
                "estimated_at": datetime.now().isoformat()
            }
            
            # Get message count
            message_count = await get_message_count(conversation_id)
            estimates["message_count"] = message_count
            
            # Rough token estimation (very approximate)
            # Average message ~100-200 tokens, summary ~400-800 tokens
            base_tokens_per_message = 150
            summary_tokens = 600
            
            if include_context:
                # Check if summary exists
                has_summary = False
                try:
                    summary = await get_latest_summary(conversation_id)
                    has_summary = summary is not None
                    if summary:
                        summary_tokens = len(summary["summary_content"]) // 3  # Rough estimate
                except:
                    pass
                
                if has_summary:
                    # Recent messages + summary
                    recent_count = min(10, message_count)
                    estimated_tokens = (recent_count * base_tokens_per_message) + summary_tokens
                    estimates["context_type"] = "summary + recent"
                    estimates["includes_summary"] = True
                else:
                    # All messages (up to limit)
                    context_messages = min(message_count, 20)
                    estimated_tokens = context_messages * base_tokens_per_message
                    estimates["context_type"] = "full history"
                    estimates["includes_summary"] = False
            else:
                estimated_tokens = 0
                estimates["context_type"] = "none"
            
            estimates["estimated_tokens"] = estimated_tokens
            estimates["optimization_potential"] = max(0, (message_count * base_tokens_per_message) - estimated_tokens)
            
            return estimates
            
        except Exception as e:
            logger.error(f"Failed to estimate token usage: {e}")
            return {"conversation_id": conversation_id, "error": str(e)}
    
    async def check_conversation_health(
        self, 
        conversation_id: str
    ) -> Dict[str, Any]:
        """Check conversation health and recommend optimizations"""
        try:
            message_count = await get_message_count(conversation_id)
            token_estimates = await self.estimate_token_usage(conversation_id)
            
            health_status = {
                "conversation_id": conversation_id,
                "message_count": message_count,
                "health_score": 10,  # Start with perfect score
                "recommendations": [],
                "status": "healthy"
            }
            
            # Assess health based on message count
            if message_count > 50:
                health_status["health_score"] -= 4
                health_status["recommendations"].append("Consider archiving old conversation")
                health_status["status"] = "needs_attention"
            elif message_count > 30:
                health_status["health_score"] -= 2
                health_status["recommendations"].append("Create summary to optimize token usage")
                health_status["status"] = "warning"
            elif message_count > self.max_context_messages:
                health_status["health_score"] -= 1
                health_status["recommendations"].append("Consider summarization")
            
            # Check if summary exists for long conversations
            if message_count > 20:
                try:
                    summary = await get_latest_summary(conversation_id)
                    if not summary:
                        health_status["recommendations"].append("Create conversation summary")
                        health_status["health_score"] -= 1
                    else:
                        health_status["health_score"] += 1  # Bonus for having summary
                        health_status["has_summary"] = True
                except:
                    pass
            
            # Token usage assessment
            estimated_tokens = token_estimates.get("estimated_tokens", 0)
            if estimated_tokens > 3000:
                health_status["recommendations"].append("High token usage - optimize context")
                health_status["health_score"] -= 2
            
            # Final health categorization
            if health_status["health_score"] >= 8:
                health_status["status"] = "healthy"
            elif health_status["health_score"] >= 6:
                health_status["status"] = "warning"
            else:
                health_status["status"] = "needs_attention"
            
            health_status["token_estimates"] = token_estimates
            
            return health_status
            
        except Exception as e:
            logger.error(f"Failed to check conversation health: {e}")
            return {
                "conversation_id": conversation_id,
                "status": "error",
                "error": str(e)
            }