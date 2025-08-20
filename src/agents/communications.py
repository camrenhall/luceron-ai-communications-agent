"""
Communications agent implementation
"""
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage

from src.config.settings import ANTHROPIC_API_KEY
from src.services.prompt_loader import load_prompt
from src.tools.case_analysis import GetCaseAnalysisTool
from src.tools.case_lookup import IntelligentCaseLookupTool
from src.tools.case_verification import VerifyCaseDetailsTool, RequestClarificationTool
from src.tools.email_composer import ComposeEmailTool
from src.tools.email_sender import SendEmailTool
from src.tools.case_creator import CreateCaseTool
from src.tools.document_manager import (
    UpdateDocumentStatusTool,
    GetDocumentStatusTool,
    GetPendingRemindersTool
)


def create_communications_agent() -> AgentExecutor:
    """Create a communications agent"""
    llm = ChatAnthropic(
        model="claude-3-5-sonnet-20241022",
        api_key=ANTHROPIC_API_KEY,
        temperature=0.1
    )
    
    tools = [
        IntelligentCaseLookupTool(),
        GetCaseAnalysisTool(),
        VerifyCaseDetailsTool(),
        RequestClarificationTool(),
        ComposeEmailTool(),
        SendEmailTool(),
        CreateCaseTool(),
        UpdateDocumentStatusTool(),
        GetDocumentStatusTool(),
        GetPendingRemindersTool()
    ]
    
    system_prompt = load_prompt("enhanced_communications_system_prompt.md")
    
    prompt = ChatPromptTemplate.from_messages([
        SystemMessage(content=system_prompt),
        MessagesPlaceholder("conversation_history", optional=True),
        ("human", "{input}"),
        MessagesPlaceholder("agent_scratchpad")
    ])
    
    agent = create_tool_calling_agent(llm, tools, prompt)
    
    return AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        max_iterations=10
    )