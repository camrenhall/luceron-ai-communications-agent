#!/usr/bin/env python3
"""
Test script for the intelligent case lookup functionality
"""
import asyncio
import json
from unittest.mock import AsyncMock, patch

# Mock the search API response for testing
MOCK_SEARCH_RESPONSES = {
    "single_exact_match": [
        {
            "case_id": "12345678-1234-1234-1234-123456789abc",
            "client_name": "Camren Hall",
            "client_email": "camren@example.com",
            "client_phone": "+1234567890",
            "status": "OPEN",
            "created_at": "2024-01-15T10:00:00Z"
        }
    ],
    "multiple_matches": [
        {
            "case_id": "11111111-1111-1111-1111-111111111111",
            "client_name": "John Smith",
            "client_email": "john.smith@example.com",
            "status": "OPEN"
        },
        {
            "case_id": "22222222-2222-2222-2222-222222222222", 
            "client_name": "John Davis",
            "client_email": "john.davis@example.com",
            "status": "OPEN"
        },
        {
            "case_id": "33333333-3333-3333-3333-333333333333",
            "client_name": "John Wilson", 
            "client_email": "john.wilson@example.com",
            "status": "OPEN"
        }
    ],
    "no_matches": [],
    "fuzzy_match": [
        {
            "case_id": "44444444-4444-4444-4444-444444444444",
            "client_name": "Cameron Hall",
            "client_email": "cameron@example.com", 
            "status": "OPEN"
        }
    ]
}


async def test_case_lookup_scenarios():
    """Test various case lookup scenarios"""
    
    print("🧪 Testing Intelligent Case Lookup System")
    print("=" * 50)
    
    # Test 1: Single exact match (high confidence)
    print("\n📋 Test 1: Single Exact Match")
    print("Input: 'Camren'")
    print("Expected: High confidence, auto-proceed")
    
    with patch('src.services.backend_api.search_cases_by_name', 
               new_callable=AsyncMock) as mock_search:
        mock_search.return_value = MOCK_SEARCH_RESPONSES["single_exact_match"]
        
        # Simulate the lookup logic
        result = await simulate_lookup("Camren", mock_search)
        print(f"Result: {result['action']}")
        print(f"Confidence: {result.get('confidence', 'N/A')}")
        if result['action'] == 'proceed_with_case':
            print(f"✅ Found: {result['case']['client_name']} ({result['case']['client_email']})")
    
    # Test 2: Multiple matches (low confidence)
    print("\n📋 Test 2: Multiple Matches")
    print("Input: 'John'")
    print("Expected: Low confidence, request clarification")
    
    with patch('src.services.backend_api.search_cases_by_name',
               new_callable=AsyncMock) as mock_search:
        mock_search.return_value = MOCK_SEARCH_RESPONSES["multiple_matches"]
        
        result = await simulate_lookup("John", mock_search)
        print(f"Result: {result['action']}")
        print(f"Matches found: {len(result.get('matches', []))}")
        if result['action'] == 'request_clarification':
            print(f"✅ Clarification requested: {result['clarification_request']}")
    
    # Test 3: No matches
    print("\n📋 Test 3: No Matches")
    print("Input: 'Alice'")
    print("Expected: No matches, suggest alternatives")
    
    with patch('src.services.backend_api.search_cases_by_name',
               new_callable=AsyncMock) as mock_search:
        mock_search.return_value = MOCK_SEARCH_RESPONSES["no_matches"]
        
        result = await simulate_lookup("Alice", mock_search)
        print(f"Result: {result['action']}")
        if result['action'] == 'suggest_new_case':
            print(f"✅ Suggestion: {result['message']}")
    
    # Test 4: Fuzzy match (medium confidence)
    print("\n📋 Test 4: Fuzzy Match")
    print("Input: 'Camren' (searching for 'Cameron')")
    print("Expected: Medium confidence, verify and proceed")
    
    with patch('src.services.backend_api.search_cases_by_name',
               new_callable=AsyncMock) as mock_search:
        mock_search.return_value = MOCK_SEARCH_RESPONSES["fuzzy_match"]
        
        result = await simulate_lookup("Camren", mock_search)
        print(f"Result: {result['action']}")
        print(f"Confidence: {result.get('confidence', 'N/A')}")
        if result['action'] == 'proceed_with_case':
            print(f"✅ Fuzzy match: '{result['case']['client_name']}' for input 'Camren'")
    
    print("\n🎉 All tests completed!")


async def simulate_lookup(client_name: str, mock_search_func):
    """Simulate the lookup logic"""
    
    # This simulates the core logic from IntelligentCaseLookupTool
    normalized_name = client_name.strip().title()
    
    # Search OPEN cases
    open_cases = await mock_search_func(
        client_name=normalized_name,
        status="OPEN",
        use_fuzzy=True,
        fuzzy_threshold=0.3
    )
    
    # Analyze confidence
    if not open_cases:
        return {
            "action": "suggest_new_case",
            "message": f"No cases found for '{client_name}'. Would you like me to create a new case?"
        }
    
    if len(open_cases) == 1:
        case = open_cases[0]
        similarity = calculate_similarity(normalized_name, case["client_name"])
        
        if similarity >= 0.9:
            confidence = 100
        elif similarity >= 0.7:
            confidence = 85
        else:
            confidence = 70
            
        return {
            "action": "proceed_with_case",
            "confidence": confidence,
            "case": case
        }
    else:
        # Multiple matches
        return {
            "action": "request_clarification",
            "confidence": 40,
            "matches": open_cases,
            "clarification_request": f"I found {len(open_cases)} clients that could match '{client_name}'. Could you provide more details?"
        }


def calculate_similarity(search_name: str, case_name: str) -> float:
    """Simple similarity calculation"""
    search_lower = search_name.lower()
    case_lower = case_name.lower()
    
    if search_lower == case_lower:
        return 1.0
    elif search_lower in case_lower or case_lower in search_lower:
        return 0.9
    else:
        # Simple character overlap calculation
        common_chars = set(search_lower) & set(case_lower)
        total_chars = set(search_lower) | set(case_lower)
        return len(common_chars) / len(total_chars) if total_chars else 0


if __name__ == "__main__":
    asyncio.run(test_case_lookup_scenarios())