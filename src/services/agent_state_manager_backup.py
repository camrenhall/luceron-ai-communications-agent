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
        Prepare comprehensive context for agent execution
        
        Returns:
            Enhanced context dictionary for agent
        """
        try:
            agent_context = {
                "conversation_id": conversation_id,
                "agent_type": self.agent_type,
                "session_timestamp": datetime.now().isoformat()
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
                    }\n            \n            # Add conversation summary if available\n            try:\n                latest_summary = await get_latest_summary(conversation_id)\n                if latest_summary:\n                    agent_context[\"conversation_summary\"] = {\n                        \"content\": latest_summary[\"summary_content\"],\n                        \"messages_summarized\": latest_summary[\"messages_summarized\"]\n                    }\n            except Exception as e:\n                logger.debug(f\"No conversation summary available: {e}\")\n            \n            # Add recent conversation history (last 10 messages)\n            try:\n                recent_messages = await get_conversation_history(\n                    conversation_id, \n                    limit=10, \n                    include_function_calls=True\n                )\n                \n                if recent_messages:\n                    agent_context[\"recent_conversation\"] = [\n                        {\n                            \"role\": msg[\"role\"],\n                            \"content\": msg[\"content\"],\n                            \"timestamp\": msg.get(\"created_at\")\n                        }\n                        for msg in recent_messages[-5:]  # Last 5 messages\n                    ]\n            except Exception as e:\n                logger.debug(f\"Could not load recent conversation: {e}\")\n            \n            logger.info(f\"🧠 Prepared agent context with {len(agent_context)} components\")\n            return agent_context\n            \n        except Exception as e:\n            logger.error(f\"Failed to prepare agent context: {e}\")\n            return {\"conversation_id\": conversation_id, \"agent_type\": self.agent_type}\n    \n    async def store_interaction_results(\n        self,\n        case_id: Optional[str],\n        final_response: str,\n        agent_result: Dict[str, Any]\n    ) -> None:\n        \"\"\"Store important findings and interactions in case context\"\"\"\n        if not case_id or case_id == \"general\":\n            return\n        \n        try:\n            context_updates = await self._analyze_interaction_for_context(\n                final_response, agent_result\n            )\n            \n            # Store each context update\n            for key, value in context_updates.items():\n                await store_agent_context(\n                    case_id=case_id,\n                    agent_type=self.agent_type,\n                    context_key=key,\n                    context_value=value,\n                    expires_at=None  # Permanent storage for important findings\n                )\n                logger.info(f\"💾 Stored context '{key}' for case {case_id}\")\n            \n        except Exception as e:\n            logger.warning(f\"Failed to store interaction results: {e}\")\n    \n    async def _analyze_interaction_for_context(\n        self,\n        final_response: str, \n        agent_result: Dict[str, Any]\n    ) -> Dict[str, Dict[str, Any]]:\n        \"\"\"Analyze agent interaction to extract context-worthy information\"\"\"\n        context_updates = {}\n        current_time = datetime.now().isoformat()\n        \n        # Detect communication preferences\n        if any(word in final_response.lower() for word in [\"formal\", \"professional\", \"casual\", \"friendly\"]):\n            style = \"formal\" if any(word in final_response.lower() for word in [\"formal\", \"professional\"]) else \"casual\"\n            context_updates[\"client_preferences\"] = {\n                \"communication_style\": style,\n                \"detected_at\": current_time,\n                \"confidence\": \"inferred\",\n                \"source\": \"agent_response_analysis\"\n            }\n        \n        # Detect email interactions\n        email_indicators = [\"email sent\", \"reminder sent\", \"emailed\", \"contacted\"]\n        if any(indicator in final_response.lower() for indicator in email_indicators):\n            context_updates[\"email_history\"] = {\n                \"last_email_sent\": current_time,\n                \"email_count\": 1,  # This would be incremented in real implementation\n                \"last_email_type\": \"reminder\" if \"reminder\" in final_response.lower() else \"general\",\n                \"effectiveness\": \"sent\"  # Could be enhanced with tracking\n            }\n        \n        # Detect case management activities\n        case_activities = [\"case created\", \"documents requested\", \"client contacted\"]\n        if any(activity in final_response.lower() for activity in case_activities):\n            context_updates[\"case_progress\"] = {\n                \"last_activity\": current_time,\n                \"activity_type\": \"case_management\",\n                \"description\": final_response[:200] + \"...\" if len(final_response) > 200 else final_response,\n                \"agent_action\": True\n            }\n        \n        # Detect client feedback or preferences mentioned\n        if \"client said\" in final_response.lower() or \"client mentioned\" in final_response.lower():\n            context_updates[\"client_feedback\"] = {\n                \"timestamp\": current_time,\n                \"feedback_source\": \"agent_interaction\",\n                \"content\": final_response[:300],\n                \"requires_follow_up\": \"follow up\" in final_response.lower()\n            }\n        \n        return context_updates\n    \n    async def get_conversation_metrics(self, conversation_id: str) -> Dict[str, Any]:\n        \"\"\"Get metrics and insights about the conversation\"\"\"\n        try:\n            message_count = await get_message_count(conversation_id)\n            recent_messages = await get_conversation_history(conversation_id, limit=5)\n            latest_summary = await get_latest_summary(conversation_id)\n            \n            metrics = {\n                \"message_count\": message_count,\n                \"has_summary\": latest_summary is not None,\n                \"recent_activity\": len(recent_messages),\n                \"conversation_health\": \"active\" if message_count < 30 else \"needs_summary\"\n            }\n            \n            if latest_summary:\n                metrics[\"summary_info\"] = {\n                    \"messages_summarized\": latest_summary[\"messages_summarized\"],\n                    \"tokens_saved\": latest_summary.get(\"tokens_saved\")\n                }\n            \n            return metrics\n            \n        except Exception as e:\n            logger.error(f\"Failed to get conversation metrics: {e}\")\n            return {\"message_count\": 0, \"has_summary\": False}