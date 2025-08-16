"""
Prompt loading utilities
"""
import os
from typing import Dict


def load_prompt(filename: str) -> str:
    """Load prompt from markdown file"""
    prompt_path = os.path.join("prompts", filename)
    with open(prompt_path, 'r', encoding='utf-8') as f:
        return f.read().strip()


def load_email_templates() -> Dict[str, Dict[str, str]]:
    """Load email templates from markdown file"""
    template_content = load_prompt("email_templates.md")
    
    # Simple parsing - extract templates between ## headers
    templates = {}
    lines = template_content.split('\n')
    current_template = None
    current_body = []
    in_body = False
    
    for line in lines:
        if line.startswith('## ') and 'Template' in line:
            # Save previous template
            if current_template and current_body:
                templates[current_template]['body_template'] = '\n'.join(current_body).strip()
            
            # Start new template
            template_name = line.replace('## ', '').replace(' Template', '').lower().replace(' ', '_').replace('-', '_')
            current_template = template_name
            templates[current_template] = {}
            current_body = []
            in_body = False
            
        elif line.startswith('**Subject**:') and current_template:
            subject = line.replace('**Subject**:', '').strip()
            templates[current_template]['subject_template'] = subject
            
        elif line.startswith('**Body**:') and current_template:
            in_body = True
            current_body = []
            
        elif line.startswith('**Tone**:') and current_template:
            tone = line.replace('**Tone**:', '').strip()
            templates[current_template]['tone'] = tone
            in_body = False
            
        elif in_body and line.strip() and not line.startswith('```'):
            current_body.append(line)
    
    # Save last template
    if current_template and current_body:
        templates[current_template]['body_template'] = '\n'.join(current_body).strip()
    
    # Add aliases for common variations
    if 'initial_reminder' in templates:
        templates['initial_document_request'] = templates['initial_reminder']
        templates['initial_contact'] = templates['initial_reminder']
    
    return templates