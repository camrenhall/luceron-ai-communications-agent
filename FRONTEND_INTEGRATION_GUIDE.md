# Communications Agent Frontend Integration Guide

## Overview

This guide provides complete integration instructions for the enhanced Communications Agent streaming architecture. The new system provides real-time streaming of agent reasoning chains and final responses.

## API Endpoints

### Primary Endpoint

- **POST `/chat`** - Enhanced streaming chat endpoint with real-time reasoning
- **GET `/api/workflows/{workflow_id}`** - Retrieve complete workflow data (fallback)
- **GET `/api/workflows/{workflow_id}/status`** - Get workflow status only (lightweight)

## Streaming Event Types

The enhanced SSE stream provides the following event types:

### 1. Workflow Started
```json
{
  "type": "workflow_started",
  "workflow_id": "wf_12345abc",
  "timestamp": "2025-08-19T15:30:00.000Z",
  "initial_prompt": "Find cases for client John Smith",
  "agent_type": "CommunicationsAgent"
}
```

### 2. Reasoning Step
```json
{
  "type": "reasoning_step",
  "workflow_id": "wf_12345abc",
  "timestamp": "2025-08-19T15:30:01.500Z",
  "step_id": "step_789xyz",
  "thought": "I need to search for cases with client name John Smith",
  "action": "IntelligentCaseLookupTool",
  "action_input": {"client_name": "John Smith"},
  "step_number": 1
}
```

### 3. Tool Start
```json
{
  "type": "tool_start",
  "workflow_id": "wf_12345abc",
  "timestamp": "2025-08-19T15:30:02.000Z",
  "tool_name": "IntelligentCaseLookupTool",
  "tool_input": {"client_name": "John Smith"},
  "description": "Search for cases by client name"
}
```

### 4. Tool End
```json
{
  "type": "tool_end",
  "workflow_id": "wf_12345abc",
  "timestamp": "2025-08-19T15:30:04.500Z",
  "tool_name": "IntelligentCaseLookupTool",
  "tool_output": "Found 3 cases for John Smith...",
  "success": true,
  "execution_time_ms": 2500
}
```

### 5. Agent Thinking
```json
{
  "type": "agent_thinking",
  "workflow_id": "wf_12345abc",
  "timestamp": "2025-08-19T15:30:05.000Z",
  "thinking": "Based on the search results, I found 3 active cases...",
  "planning_stage": "analysis"
}
```

### 6. Workflow Completed
```json
{
  "type": "workflow_completed",
  "workflow_id": "wf_12345abc",
  "timestamp": "2025-08-19T15:30:15.000Z",
  "final_response": "I found 3 active cases for John Smith: Case #123...",
  "total_steps": 5,
  "execution_time_ms": 15000,
  "tools_used": ["IntelligentCaseLookupTool", "GetCaseAnalysisTool"]
}
```

### 7. Workflow Error
```json
{
  "type": "workflow_error",
  "workflow_id": "wf_12345abc",
  "timestamp": "2025-08-19T15:30:10.000Z",
  "error_message": "Database connection timeout",
  "error_type": "ConnectionError",
  "recovery_suggestion": "Please try again in a moment",
  "partial_response": "I was able to find 2 cases before the error..."
}
```

### 8. Heartbeat
```json
{
  "type": "heartbeat",
  "workflow_id": "wf_12345abc",
  "timestamp": "2025-08-19T15:30:30.000Z",
  "status": "processing"
}
```

## Frontend Implementation Examples

### JavaScript/TypeScript Implementation

```typescript
interface StreamEvent {
  type: string;
  workflow_id: string;
  timestamp: string;
  [key: string]: any;
}

class CommunicationsAgentClient {
  private baseUrl: string;
  private currentWorkflowId: string | null = null;
  
  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }
  
  async sendMessage(message: string): Promise<AsyncIterable<StreamEvent>> {
    const response = await fetch(`${this.baseUrl}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream'
      },
      body: JSON.stringify({ message })
    });
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    
    return this.parseSSEStream(response);
  }
  
  private async* parseSSEStream(response: Response): AsyncIterable<StreamEvent> {
    const reader = response.body?.getReader();
    const decoder = new TextDecoder();
    
    if (!reader) {
      throw new Error('No response body');
    }
    
    let buffer = '';
    
    try {
      while (true) {
        const { done, value } = await reader.read();
        
        if (done) {
          break;
        }
        
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const eventData = JSON.parse(line.slice(6));
              yield eventData as StreamEvent;
              
              // Track workflow ID from first event
              if (eventData.workflow_id && !this.currentWorkflowId) {
                this.currentWorkflowId = eventData.workflow_id;
              }
            } catch (e) {
              console.warn('Failed to parse SSE event:', line);
            }
          }
        }
      }
    } finally {
      reader.releaseLock();
    }
  }
  
  // Fallback method to get workflow data
  async getWorkflowData(workflowId: string): Promise<any> {
    const response = await fetch(`${this.baseUrl}/api/workflows/${workflowId}`);
    
    if (!response.ok) {
      throw new Error(`Failed to get workflow: ${response.statusText}`);
    }
    
    return response.json();
  }
  
  // Lightweight status check
  async getWorkflowStatus(workflowId: string): Promise<any> {
    const response = await fetch(`${this.baseUrl}/api/workflows/${workflowId}/status`);
    
    if (!response.ok) {
      throw new Error(`Failed to get status: ${response.statusText}`);
    }
    
    return response.json();
  }
}
```

### React Chat Component Example

```tsx
import React, { useState, useCallback, useRef, useEffect } from 'react';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  workflowId?: string;
  reasoningSteps?: any[];
  isStreaming?: boolean;
}

interface ReasoningStep {
  step_id: string;
  thought: string;
  action?: string;
  timestamp: string;
  tool_name?: string;
  execution_time_ms?: number;
}

const ChatInterface: React.FC = () => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [showReasoning, setShowReasoning] = useState<Record<string, boolean>>({});
  const [currentReasoning, setCurrentReasoning] = useState<ReasoningStep[]>([]);
  const [currentWorkflowId, setCurrentWorkflowId] = useState<string | null>(null);
  
  const agentClient = useRef(new CommunicationsAgentClient('/api'));
  
  const sendMessage = useCallback(async () => {
    if (!inputMessage.trim() || isLoading) return;
    
    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: inputMessage,
      timestamp: new Date()
    };
    
    setMessages(prev => [...prev, userMessage]);
    setInputMessage('');
    setIsLoading(true);
    setCurrentReasoning([]);
    setCurrentWorkflowId(null);
    
    // Create placeholder for agent response
    const agentMessageId = (Date.now() + 1).toString();
    const agentMessage: ChatMessage = {
      id: agentMessageId,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      reasoningSteps: [],
      isStreaming: true
    };
    
    setMessages(prev => [...prev, agentMessage]);
    
    try {
      const eventStream = await agentClient.current.sendMessage(inputMessage);
      
      for await (const event of eventStream) {
        handleStreamEvent(event, agentMessageId);
      }
    } catch (error) {
      console.error('Chat error:', error);
      setMessages(prev => prev.map(msg => 
        msg.id === agentMessageId 
          ? { ...msg, content: `Error: ${error.message}`, isStreaming: false }
          : msg
      ));
    } finally {
      setIsLoading(false);
    }
  }, [inputMessage, isLoading]);
  
  const handleStreamEvent = (event: StreamEvent, messageId: string) => {
    switch (event.type) {
      case 'workflow_started':
        setCurrentWorkflowId(event.workflow_id);
        setMessages(prev => prev.map(msg => 
          msg.id === messageId 
            ? { ...msg, workflowId: event.workflow_id }
            : msg
        ));
        break;
        
      case 'reasoning_step':
      case 'tool_start':
      case 'tool_end':
      case 'agent_thinking':
        setCurrentReasoning(prev => [...prev, event]);
        setMessages(prev => prev.map(msg => 
          msg.id === messageId 
            ? { ...msg, reasoningSteps: [...(msg.reasoningSteps || []), event] }
            : msg
        ));
        break;
        
      case 'workflow_completed':
        setMessages(prev => prev.map(msg => 
          msg.id === messageId 
            ? { 
                ...msg, 
                content: event.final_response,
                isStreaming: false,
                reasoningSteps: [...(msg.reasoningSteps || []), event]
              }
            : msg
        ));
        setCurrentReasoning([]);
        break;
        
      case 'workflow_error':
        setMessages(prev => prev.map(msg => 
          msg.id === messageId 
            ? { 
                ...msg, 
                content: event.partial_response || `Error: ${event.error_message}`,
                isStreaming: false
              }
            : msg
        ));
        setCurrentReasoning([]);
        break;
        
      case 'heartbeat':
        // Update UI to show agent is still processing
        break;
    }
  };
  
  const toggleReasoning = (messageId: string) => {
    setShowReasoning(prev => ({
      ...prev,
      [messageId]: !prev[messageId]
    }));
  };
  
  return (
    <div className="chat-interface">
      <div className="messages">
        {messages.map(message => (
          <div key={message.id} className={`message ${message.role}`}>
            <div className="message-content">
              {message.content || (message.isStreaming ? 'Agent is thinking...' : '')}
            </div>
            
            {message.reasoningSteps && message.reasoningSteps.length > 0 && (
              <div className="reasoning-section">
                <button 
                  className="reasoning-toggle"
                  onClick={() => toggleReasoning(message.id)}
                >
                  {showReasoning[message.id] ? 'Hide' : 'Show'} reasoning ({message.reasoningSteps.length} steps)
                </button>
                
                {showReasoning[message.id] && (
                  <div className="reasoning-steps">
                    {message.reasoningSteps.map((step, index) => (
                      <div key={step.step_id || index} className={`reasoning-step ${step.type}`}>
                        <div className="step-header">
                          <span className="step-type">{step.type}</span>
                          <span className="step-time">{new Date(step.timestamp).toLocaleTimeString()}</span>
                        </div>
                        
                        {step.thought && <div className="step-thought">{step.thought}</div>}
                        {step.tool_name && <div className="step-tool">Tool: {step.tool_name}</div>}
                        {step.execution_time_ms && <div className="step-timing">{step.execution_time_ms}ms</div>}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
      
      <div className="input-section">
        <input
          type="text"
          value={inputMessage}
          onChange={(e) => setInputMessage(e.target.value)}
          onKeyPress={(e) => e.key === 'Enter' && sendMessage()}
          placeholder="Ask about cases, documents, or client communications..."
          disabled={isLoading}
        />
        <button onClick={sendMessage} disabled={isLoading || !inputMessage.trim()}>
          {isLoading ? 'Processing...' : 'Send'}
        </button>
      </div>
    </div>
  );
};

export default ChatInterface;
```

### CSS Styles for Reasoning Display

```css
.chat-interface {
  display: flex;
  flex-direction: column;
  height: 100vh;
  max-width: 800px;
  margin: 0 auto;
}

.messages {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.message {
  max-width: 80%;
  padding: 12px 16px;
  border-radius: 12px;
  word-wrap: break-word;
}

.message.user {
  align-self: flex-end;
  background-color: #007bff;
  color: white;
}

.message.assistant {
  align-self: flex-start;
  background-color: #f1f3f4;
  color: #333;
  border: 1px solid #e0e0e0;
}

.reasoning-section {
  margin-top: 12px;
  border-top: 1px solid #e0e0e0;
  padding-top: 8px;
}

.reasoning-toggle {
  background: none;
  border: none;
  color: #666;
  cursor: pointer;
  font-size: 12px;
  text-decoration: underline;
}

.reasoning-toggle:hover {
  color: #007bff;
}

.reasoning-steps {
  margin-top: 8px;
  max-height: 300px;
  overflow-y: auto;
  background: #f8f9fa;
  border-radius: 6px;
  padding: 8px;
}

.reasoning-step {
  margin-bottom: 8px;
  padding: 8px;
  background: white;
  border-radius: 4px;
  border-left: 3px solid #28a745;
  font-size: 12px;
}

.reasoning-step.workflow_error {
  border-left-color: #dc3545;
}

.reasoning-step.tool_start {
  border-left-color: #ffc107;
}

.reasoning-step.tool_end {
  border-left-color: #28a745;
}

.step-header {
  display: flex;
  justify-content: space-between;
  font-weight: bold;
  margin-bottom: 4px;
}

.step-type {
  color: #007bff;
  text-transform: uppercase;
  font-size: 10px;
}

.step-time {
  color: #666;
  font-size: 10px;
}

.step-thought, .step-tool {
  margin-top: 4px;
  line-height: 1.4;
}

.step-timing {
  color: #666;
  font-style: italic;
  font-size: 10px;
  margin-top: 2px;
}

.input-section {
  display: flex;
  padding: 20px;
  border-top: 1px solid #e0e0e0;
  gap: 12px;
}

.input-section input {
  flex: 1;
  padding: 12px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 14px;
}

.input-section button {
  padding: 12px 24px;
  background-color: #007bff;
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
}

.input-section button:disabled {
  background-color: #ccc;
  cursor: not-allowed;
}
```

## Error Handling and Fallback Strategies

### 1. Stream Connection Failures
```typescript
async function handleStreamWithFallback(agentClient: CommunicationsAgentClient, message: string) {
  try {
    // Attempt streaming
    const eventStream = await agentClient.sendMessage(message);
    return { stream: eventStream, fallback: false };
  } catch (error) {
    console.warn('Streaming failed, will poll for results:', error);
    
    // Fallback: make request and poll for completion
    const response = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message })
    });
    
    // Extract workflow ID from initial response
    const workflowId = await extractWorkflowId(response);
    
    // Poll for completion
    return { workflowId, fallback: true };
  }
}

async function pollForCompletion(agentClient: CommunicationsAgentClient, workflowId: string) {
  while (true) {
    await new Promise(resolve => setTimeout(resolve, 2000)); // Wait 2 seconds
    
    const status = await agentClient.getWorkflowStatus(workflowId);
    
    if (status.status === 'COMPLETED') {
      const workflowData = await agentClient.getWorkflowData(workflowId);
      return workflowData.final_response;
    } else if (status.status === 'FAILED') {
      throw new Error('Workflow failed');
    }
    
    // Continue polling for PROCESSING status
  }
}
```

### 2. Network Reconnection
```typescript
class ResilientStreamClient {
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 3;
  
  async sendMessageWithRetry(message: string): Promise<AsyncIterable<StreamEvent>> {
    for (let attempt = 0; attempt <= this.maxReconnectAttempts; attempt++) {
      try {
        return await this.sendMessage(message);
      } catch (error) {
        if (attempt === this.maxReconnectAttempts) {
          throw error;
        }
        
        console.warn(`Stream attempt ${attempt + 1} failed, retrying...`);
        await new Promise(resolve => setTimeout(resolve, 1000 * Math.pow(2, attempt)));
      }
    }
    
    throw new Error('Max reconnection attempts exceeded');
  }
}
```

## Performance Considerations

1. **Memory Management**: Limit the number of reasoning steps displayed to prevent memory bloat
2. **Event Throttling**: Consider throttling rapid events for better UX
3. **Connection Pooling**: Reuse HTTP connections when possible
4. **Caching**: Cache workflow results for quick access

## Testing Guidelines

### CURL Testing
```bash
# Test basic streaming
curl -N -H "Accept: text/event-stream" -H "Content-Type: application/json" \
  -d '{"message": "Find cases for John Smith"}' \
  http://localhost:8082/chat

# Test fallback endpoint
curl http://localhost:8082/api/workflows/wf_12345abc

# Test status endpoint
curl http://localhost:8082/api/workflows/wf_12345abc/status
```

### Integration Testing
```typescript
describe('Communications Agent Integration', () => {
  it('should stream reasoning steps and final response', async () => {
    const client = new CommunicationsAgentClient('http://localhost:8082');
    const events: StreamEvent[] = [];
    
    const eventStream = await client.sendMessage('Test message');
    
    for await (const event of eventStream) {
      events.push(event);
      
      if (event.type === 'workflow_completed') {
        break;
      }
    }
    
    expect(events).toContainEqual(expect.objectContaining({ type: 'workflow_started' }));
    expect(events).toContainEqual(expect.objectContaining({ type: 'workflow_completed' }));
    
    const completedEvent = events.find(e => e.type === 'workflow_completed');
    expect(completedEvent.final_response).toBeTruthy();
  });
});
```

This integration guide provides everything needed for full frontend integration with the enhanced Communications Agent streaming architecture.