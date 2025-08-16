"""
Communications agent implementation
"""
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage

from app.config.settings import ANTHROPIC_API_KEY
from app.services.prompt_loader import load_prompt
from app.tools.case_analysis import GetCaseAnalysisTool
from app.tools.email_composer import ComposeEmailTool
from app.tools.email_sender import SendEmailTool
from app.tools.case_creator import CreateCaseTool


def create_communications_agent(workflow_id: str) -> AgentExecutor:
    """Create a communications agent for the given workflow"""
    llm = ChatAnthropic(
        model="claude-3-5-sonnet-20241022",
        api_key=ANTHROPIC_API_KEY,
        temperature=0.1
    )
    
    tools = [
        GetCaseAnalysisTool(),
        ComposeEmailTool(),
        SendEmailTool(),
        CreateCaseTool()
    ]
    
    system_prompt = load_prompt("communications_agent_system_prompt.md")
    
    prompt = ChatPromptTemplate.from_messages([
        SystemMessage(content=system_prompt),
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