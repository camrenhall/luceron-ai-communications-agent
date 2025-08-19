"""
Agent State Management Service

Handles conversation lifecycle, context awareness, and intelligent state management
for the Communications Agent following the Agentic Paradigm patterns.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple

from src.models.agent_state import (
    AgentType, MessageRole, ClientPreferences, EmailHistory, CaseProgress
)
from src.services.backend_api import (
    get_or_create_conversation, add_message, get_case_agent_context,
    store_agent_context, get_message_count, create_auto_summary,
    get_latest_summary, get_conversation_history
)
from src.services.token_manager import TokenManager

logger = logging.getLogger(__name__)


class AgentStateManager:
    """Manages stateful agent conversations and context"""
    
    def __init__(self, agent_type: str = AgentType.COMMUNICATIONS_AGENT.value):
        self.agent_type = agent_type
        self.token_manager = TokenManager()
        
    async def start_agent_session(
        self, 
        user_message: str,
        case_id: Optional[str] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Start a new agent session with conversation and context loading
        
        Returns:
            Tuple of (conversation_id, existing_context)
        """
        try:
            # Get or create conversation for this case/agent
            conversation_id = await get_or_create_conversation(
                case_id=case_id or "general",
                agent_type=self.agent_type
            )
            
            logger.info(f"🎯 Started agent session: conversation={conversation_id}, case={case_id}")
            
            # Add user message to conversation
            await add_message(
                conversation_id=conversation_id,
                role=MessageRole.USER,
                content={
                    "text": user_message,
                    "message_type": "user_input",
                    "session_start": True
                },
                model_used="claude-3-5-sonnet-20241022"
            )
            
            # Load existing context for this case/agent
            existing_context = {}
            if case_id:
                try:
                    existing_context = await get_case_agent_context(case_id, self.agent_type)
                    logger.info(f"📚 Loaded context keys: {list(existing_context.keys())}")
                except Exception as e:
                    logger.info(f"No existing context for case {case_id}: {e}")
            
            return conversation_id, existing_context
            
        except Exception as e:
            logger.error(f"Failed to start agent session: {e}")
            raise
    
    async def manage_conversation_length(self, conversation_id: str, threshold: int = 20) -> Dict[str, Any]:
        """
        Manage conversation length using intelligent token optimization
        
        Returns:
            Dictionary with optimization results
        """
        try:
            # Use token manager for intelligent optimization
            optimization_result = await self.token_manager.optimize_conversation_context(
                conversation_id, force_summary=False
            )
            
            if optimization_result.get("summary_created"):
                logger.info(f"⚡ Optimized conversation {conversation_id}: {optimization_result}")
            
            return optimization_result
            
        except Exception as e:
            logger.warning(f"Failed to manage conversation length: {e}")
            return {"action_taken": "error", "error": str(e)}
    
    async def prepare_agent_context(
        self, 
        conversation_id: str, 
        existing_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Prepare comprehensive context for agent execution with token optimization
        
        Returns:
            Enhanced context dictionary for agent
        """
        try:
            # Get optimized conversation context from token manager
            optimized_context = await self.token_manager.prepare_context_for_agent(
                conversation_id, max_recent_messages=10
            )
            
            agent_context = {
                "conversation_id": conversation_id,
                "agent_type": self.agent_type,
                "session_timestamp": datetime.now().isoformat(),
                "context_optimized": True
            }
            
            # Add existing case context
            if existing_context:
                agent_context["case_context"] = existing_context
                
                # Parse structured context
                if "client_preferences" in existing_context:
                    prefs = existing_context["client_preferences"]
                    agent_context["client_communication_style"] = prefs.get("communication_style", "professional")
                
                if "email_history" in existing_context:
                    email_hist = existing_context["email_history"]
                    agent_context["recent_email_activity"] = {
                        "last_email": email_hist.get("last_email_sent"),
                        "email_count": email_hist.get("email_count", 0)
                    }
            
            # Add optimized conversation context
            if "summary" in optimized_context:
                agent_context["conversation_summary"] = optimized_context["summary"]
            
            if "recent_messages" in optimized_context:
                agent_context["recent_conversation"] = optimized_context["recent_messages"]
            
            # Add token usage estimates for transparency
            try:
                token_estimates = await self.token_manager.estimate_token_usage(
                    conversation_id, include_context=True
                )
                agent_context["token_info"] = {
                    "estimated_tokens": token_estimates.get("estimated_tokens", 0),
                    "context_type": token_estimates.get("context_type", "unknown"),
                    "optimization_potential": token_estimates.get("optimization_potential", 0)
                }
            except Exception as e:
                logger.debug(f"Could not estimate token usage: {e}")
            
            logger.info(f"🧠 Prepared optimized agent context with {len(agent_context)} components")
            return agent_context
            
        except Exception as e:
            logger.error(f"Failed to prepare agent context: {e}")
            return {"conversation_id": conversation_id, "agent_type": self.agent_type}
    
    async def store_interaction_results(
        self,
        case_id: Optional[str],
        final_response: str,
        agent_result: Dict[str, Any]
    ) -> None:
        """Store important findings and interactions in case context"""
        if not case_id or case_id == "general":
            return
        
        try:
            context_updates = await self._analyze_interaction_for_context(
                final_response, agent_result
            )
            
            # Store each context update
            for key, value in context_updates.items():
                await store_agent_context(
                    case_id=case_id,
                    agent_type=self.agent_type,
                    context_key=key,
                    context_value=value,
                    expires_at=None  # Permanent storage for important findings
                )
                logger.info(f"💾 Stored context '{key}' for case {case_id}")
            
        except Exception as e:
            logger.warning(f"Failed to store interaction results: {e}")
    
    async def _analyze_interaction_for_context(
        self,
        final_response: str, 
        agent_result: Dict[str, Any]
    ) -> Dict[str, Dict[str, Any]]:
        """Analyze agent interaction to extract context-worthy information"""
        context_updates = {}
        current_time = datetime.now().isoformat()
        
        # Detect communication preferences
        if any(word in final_response.lower() for word in ["formal", "professional", "casual", "friendly"]):
            style = "formal" if any(word in final_response.lower() for word in ["formal", "professional"]) else "casual"
            context_updates["client_preferences"] = {
                "communication_style": style,
                "detected_at": current_time,
                "confidence": "inferred",
                "source": "agent_response_analysis"
            }
        
        # Detect email interactions
        email_indicators = ["email sent", "reminder sent", "emailed", "contacted"]
        if any(indicator in final_response.lower() for indicator in email_indicators):
            context_updates["email_history"] = {
                "last_email_sent": current_time,
                "email_count": 1,  # This would be incremented in real implementation
                "last_email_type": "reminder" if "reminder" in final_response.lower() else "general",
                "effectiveness": "sent"  # Could be enhanced with tracking
            }
        
        # Detect case management activities
        case_activities = ["case created", "documents requested", "client contacted"]
        if any(activity in final_response.lower() for activity in case_activities):
            context_updates["case_progress"] = {
                "last_activity": current_time,
                "activity_type": "case_management",
                "description": final_response[:200] + "..." if len(final_response) > 200 else final_response,
                "agent_action": True
            }
        
        # Detect client feedback or preferences mentioned
        if "client said" in final_response.lower() or "client mentioned" in final_response.lower():
            context_updates["client_feedback"] = {
                "timestamp": current_time,
                "feedback_source": "agent_interaction",
                "content": final_response[:300],
                "requires_follow_up": "follow up" in final_response.lower()
            }
        
        return context_updates
    
    async def get_conversation_metrics(self, conversation_id: str) -> Dict[str, Any]:
        """Get comprehensive metrics and insights about the conversation"""
        try:
            # Get basic metrics
            message_count = await get_message_count(conversation_id)
            recent_messages = await get_conversation_history(conversation_id, limit=5)
            latest_summary = await get_latest_summary(conversation_id)
            
            # Get token manager insights
            token_estimates = await self.token_manager.estimate_token_usage(conversation_id)
            health_check = await self.token_manager.check_conversation_health(conversation_id)
            
            metrics = {
                "message_count": message_count,
                "has_summary": latest_summary is not None,
                "recent_activity": len(recent_messages),
                "conversation_health": health_check.get("status", "unknown"),
                "health_score": health_check.get("health_score", 0),
                "token_estimates": token_estimates,
                "recommendations": health_check.get("recommendations", [])
            }
            
            if latest_summary:
                metrics["summary_info"] = {
                    "messages_summarized": latest_summary["messages_summarized"],
                    "tokens_saved": latest_summary.get("tokens_saved")
                }
            
            return metrics
            
        except Exception as e:
            logger.error(f"Failed to get conversation metrics: {e}")
            return {"message_count": 0, "has_summary": False}