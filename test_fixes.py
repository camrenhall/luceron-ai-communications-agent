#!/usr/bin/env python3
"""
Test the critical fixes for streaming architecture
"""
import asyncio
import sys
import os
from datetime import datetime

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_streaming_session_fix():
    """Test that streaming session context manager works correctly"""
    print("🔍 Testing streaming session fix...")
    
    try:
        from src.services.streaming_coordinator import streaming_session, get_streaming_coordinator
        
        workflow_id = "test_fix_123"
        
        # Test that streaming_session yields an async generator, not individual events
        async with streaming_session(workflow_id, "test message") as event_stream:
            # This should work now - event_stream should be an async generator
            events_collected = []
            
            async for event in event_stream:
                events_collected.append(event)
                if len(events_collected) >= 2:  # Just collect a couple events
                    break
            
            print(f"  ✅ Collected {len(events_collected)} events")
            print(f"  ✅ Event types: {[e.type for e in events_collected]}")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Streaming session test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_callback_handler_fix():
    """Test that callback handler handles None serialized parameters"""
    print("🔍 Testing callback handler fix...")
    
    try:
        from src.agents.callbacks import StreamingWorkflowCallbackHandler
        
        workflow_id = "test_callback_456"
        handler = StreamingWorkflowCallbackHandler(workflow_id, enable_backend_persistence=False)
        
        # Test on_chain_start with None serialized (this was causing the error)
        try:
            await handler.on_chain_start(None, {})
            print("  ✅ on_chain_start with None serialized handled")
        except Exception as e:
            print(f"  ❌ on_chain_start failed: {e}")
            return False
        
        # Test on_tool_start with None serialized
        try:
            await handler.on_tool_start(None, "test input")
            print("  ✅ on_tool_start with None serialized handled")
        except Exception as e:
            print(f"  ❌ on_tool_start failed: {e}")
            return False
        
        return True
        
    except Exception as e:
        print(f"  ❌ Callback handler test failed: {e}")
        return False


async def test_error_handling_fix():
    """Test enhanced error handling"""
    print("🔍 Testing error handling fix...")
    
    try:
        from src.services.streaming_coordinator import get_streaming_coordinator
        
        coordinator = await get_streaming_coordinator()
        workflow_id = "test_error_789"
        
        # Test error workflow with recovery suggestion
        await coordinator.error_workflow(
            workflow_id,
            "The AI service is currently overloaded",
            "OverloadedError",
            recovery_suggestion="Please try again in a few moments"
        )
        
        print("  ✅ Error workflow with recovery suggestion works")
        
        # Cleanup
        await coordinator.stop()
        
        return True
        
    except Exception as e:
        print(f"  ❌ Error handling test failed: {e}")
        return False


async def test_simple_event_flow():
    """Test a complete simple event flow"""
    print("🔍 Testing simple event flow...")
    
    try:
        from src.services.streaming_coordinator import StreamingCoordinator
        from src.models.streaming import WorkflowStartedEvent
        
        # Create local coordinator for testing
        coordinator = StreamingCoordinator()
        await coordinator.start()
        
        workflow_id = "test_flow_abc"
        events_received = []
        
        # Create event consumer
        async def consume_events():
            async for event in coordinator.create_stream(workflow_id, "test"):
                events_received.append(event)
                if event.type == "workflow_completed":
                    break
        
        # Start consumer
        consumer_task = asyncio.create_task(consume_events())
        
        # Give it time to start
        await asyncio.sleep(0.1)
        
        # Complete the workflow
        await coordinator.complete_workflow(workflow_id, "Test response", 1000)
        
        # Wait for completion
        await asyncio.wait_for(consumer_task, timeout=3.0)
        
        event_types = [e.type for e in events_received]
        print(f"  ✅ Received events: {event_types}")
        
        # Cleanup
        await coordinator.stop()
        
        return "workflow_started" in event_types and "workflow_completed" in event_types
        
    except Exception as e:
        print(f"  ❌ Event flow test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def run_fix_tests():
    """Run all fix validation tests"""
    print("🚀 Testing Critical Fixes for Streaming Architecture\n")
    
    tests = [
        ("Streaming Session Fix", test_streaming_session_fix),
        ("Callback Handler Fix", test_callback_handler_fix),
        ("Error Handling Fix", test_error_handling_fix),
        ("Simple Event Flow", test_simple_event_flow)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"📋 {test_name}")
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"  ❌ {test_name} failed with exception: {e}")
            results.append((test_name, False))
        print()
    
    # Summary
    print("=" * 60)
    print("🎯 FIX VALIDATION SUMMARY")
    print("=" * 60)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status:8} {test_name}")
        if result:
            passed += 1
    
    print(f"\nResults: {passed}/{total} fixes validated")
    
    if passed == total:
        print("🎉 All critical fixes working! Ready to test with agent.")
        return True
    else:
        print("⚠️  Some fixes still have issues.")
        return False


if __name__ == "__main__":
    try:
        result = asyncio.run(run_fix_tests())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n⛔ Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Fatal error: {e}")
        sys.exit(1)