"""
Intelligent case lookup tool with name-based search and disambiguation
"""
import json
import re
from typing import List, Dict, Any, Optional, Tuple
from langchain.tools import BaseTool
from difflib import SequenceMatcher

from src.services.backend_api import search_cases_by_name


class IntelligentCaseLookupTool(BaseTool):
    name: str = "lookup_case_by_name"
    description: str = """Intelligently find a case by client name with automatic disambiguation.
    Input should be the client name mentioned by the user (e.g., 'Camren', 'John Smith', 'Sarah').
    This tool will search for matching cases and either return the case details or ask for clarification
    if multiple matches are found."""
    
    def _run(self, client_name: str) -> str:
        raise NotImplementedError("Use async version")
    
    async def _arun(self, client_name: str) -> str:
        """
        Intelligently lookup case by name with progressive disambiguation
        """
        # Clean and normalize the input name
        normalized_name = self._normalize_name(client_name)
        
        # Stage 1: Search OPEN cases with fuzzy matching
        open_cases = await search_cases_by_name(
            client_name=normalized_name,
            status="OPEN",
            use_fuzzy=True,
            fuzzy_threshold=0.3
        )
        
        # Analyze confidence and determine next action
        confidence_result = self._analyze_confidence(normalized_name, open_cases)
        
        if confidence_result["action"] == "proceed":
            # High confidence - return the case details
            case = confidence_result["case"]
            return json.dumps({
                "status": "success",
                "confidence": confidence_result["confidence"],
                "action": "proceed_with_case",
                "case": case,
                "message": f"Found case for {case['client_name']} (ID: {case['case_id']})"
            }, indent=2)
            
        elif confidence_result["action"] == "clarify":
            # Multiple matches - need clarification
            return json.dumps({
                "status": "needs_clarification",
                "confidence": confidence_result["confidence"],
                "action": "request_clarification",
                "matches": confidence_result["matches"],
                "clarification_request": confidence_result["clarification_message"],
                "suggested_questions": confidence_result["suggested_questions"]
            }, indent=2)
            
        else:
            # No matches in OPEN cases - try CLOSED cases
            closed_cases = await search_cases_by_name(
                client_name=normalized_name,
                status="CLOSED",
                use_fuzzy=True,
                fuzzy_threshold=0.3
            )
            
            if closed_cases:
                return json.dumps({
                    "status": "found_closed_cases",
                    "action": "confirm_closed_case",
                    "matches": closed_cases[:5],  # Limit to top 5
                    "message": f"No open cases found for '{client_name}', but found {len(closed_cases)} closed case(s). Did you mean one of these closed cases, or should we create a new case?"
                }, indent=2)
            else:
                return json.dumps({
                    "status": "no_matches",
                    "action": "suggest_new_case",
                    "message": f"No cases found for '{client_name}'. Would you like me to create a new case for this client?"
                }, indent=2)
    
    def _normalize_name(self, name: str) -> str:
        """Normalize name for better matching"""
        # Remove extra whitespace and convert to title case
        normalized = re.sub(r'\s+', ' ', name.strip()).title()
        return normalized
    
    def _analyze_confidence(self, search_name: str, cases: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze search results and determine confidence level and required action
        """
        if not cases:
            return {"action": "no_matches", "confidence": 0}
        
        if len(cases) == 1:
            case = cases[0]
            similarity = self._calculate_name_similarity(search_name, case["client_name"])
            
            if similarity >= 0.9:  # Very high similarity
                return {
                    "action": "proceed",
                    "confidence": 100,
                    "case": case
                }
            elif similarity >= 0.7:  # Good similarity
                return {
                    "action": "proceed", 
                    "confidence": 85,
                    "case": case
                }
            else:  # Lower similarity but only match
                return {
                    "action": "proceed",
                    "confidence": 70,
                    "case": case
                }
        
        # Multiple matches - need disambiguation
        scored_matches = []
        for case in cases:
            similarity = self._calculate_name_similarity(search_name, case["client_name"])
            scored_matches.append({
                **case,
                "similarity_score": similarity
            })
        
        # Sort by similarity
        scored_matches.sort(key=lambda x: x["similarity_score"], reverse=True)
        
        # Generate clarification strategy
        clarification_strategy = self._generate_clarification_strategy(search_name, scored_matches)
        
        return {
            "action": "clarify",
            "confidence": 40,  # Multiple matches = low confidence
            "matches": scored_matches[:5],  # Top 5 matches
            "clarification_message": clarification_strategy["message"],
            "suggested_questions": clarification_strategy["questions"]
        }
    
    def _calculate_name_similarity(self, search_name: str, case_name: str) -> float:
        """Calculate similarity between search name and case name"""
        # Normalize both names for comparison
        search_normalized = search_name.lower().strip()
        case_normalized = case_name.lower().strip()
        
        # Check for exact match
        if search_normalized == case_normalized:
            return 1.0
        
        # Check if search name is contained in case name (for partial matches like "Camren" in "Camren Hall")
        if search_normalized in case_normalized or case_normalized in search_normalized:
            return 0.9
        
        # Use sequence matcher for fuzzy matching
        return SequenceMatcher(None, search_normalized, case_normalized).ratio()
    
    def _generate_clarification_strategy(self, search_name: str, matches: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generate intelligent clarification questions based on available data
        """
        # Analyze what differentiating information is available
        has_emails = any(match.get("client_email") for match in matches)
        has_phones = any(match.get("client_phone") for match in matches)
        
        # Check if names are very similar (suggesting we need last name)
        similar_names = [match["client_name"] for match in matches if 
                        self._calculate_name_similarity(search_name, match["client_name"]) > 0.7]
        
        if len(similar_names) > 1:
            # Very similar names - ask for full name or last name
            message = f"I found {len(matches)} clients with similar names to '{search_name}'. Could you provide the full name or last name to help me identify the correct case?"
            questions = [
                "What is the client's full name?",
                "What is their last name?",
                "Do you have their email or phone number?"
            ]
        elif has_phones and has_emails:
            # Multiple clients, have contact info - ask for identifying info
            message = f"I found {len(matches)} clients named '{search_name}'. Could you provide additional information to identify the correct case?"
            questions = [
                "What is their email address?", 
                "What is their phone number?",
                "What is their full name?"
            ]
        else:
            # Multiple clients, limited info - ask for any additional details
            message = f"I found {len(matches)} cases that could match '{search_name}'. Could you provide more details to help identify the correct case?"
            questions = [
                "What is their full name?",
                "Do you have their contact information?",
                "When was this case created approximately?"
            ]
        
        return {
            "message": message,
            "questions": questions
        }