import os
import json
import logging
from typing import Dict, Optional
import anthropic
import streamlit as st

class NaturalLanguageQueryGenerator:
    """
    Converts natural language queries into SQL SELECT statements for the finance database.
    """
    
    def __init__(self, api_key: str = None):
        """Initialize the SQL query generator with Claude API client
        
        Args:
            api_key: Anthropic API key
        """
        # Try to get API key from multiple sources
        if api_key:
            self.api_key = api_key
        elif hasattr(st, 'secrets') and "anthropic" in st.secrets and "api_key" in st.secrets["anthropic"]:
            self.api_key = st.secrets["anthropic"]["api_key"]
        
        if not self.api_key:
            raise ValueError(
                "Anthropic API key not found. "
                "Please add it to Streamlit secrets under [anthropic] api_key "
                "or set ANTHROPIC_API_KEY environment variable."
            )
        
        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.logger = logging.getLogger(__name__)
        
        # Model configuration
        self.model = "claude-sonnet-4-20250514"
        self.max_tokens = 1500
        
        # Load the SQL generation prompt
        self.prompt_template = self._load_prompt_template()
    
    def _load_prompt_template(self) -> str:
        """Load the SQL generation prompt template"""
        prompt_path = os.path.join(os.path.dirname(__file__), 'prompts', 'sql_generation_prompt.md')
        try:
            with open(prompt_path, 'r') as f:
                return f.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"SQL generation prompt template not found at {prompt_path}. Please create the prompt file.")
    
    def generate_sql_query(self, natural_language_query: str) -> Dict[str, str]:
        """
        Convert natural language query to SQL
        
        Args:
            natural_language_query: User's natural language question
            
        Returns:
            Dict with 'sql_query' and 'explanation' keys, or error info
        """
        try:
            # Format the prompt with the user's query
            prompt = self.prompt_template.format(query=natural_language_query)
            
            # Call Claude API
            message = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=0.1,
                messages=[{"role": "user", "content": prompt}]
            )
            
            # Extract response text
            if hasattr(message.content[0], 'text'):
                response_text = message.content[0].text.strip()
            else:
                raise ValueError("No text response from LLM")
            
            # Clean up the response - remove any markdown code blocks
            sql_query = response_text
            if sql_query.startswith('```sql'):
                sql_query = sql_query[6:]
            if sql_query.startswith('```'):
                sql_query = sql_query[3:]
            if sql_query.endswith('```'):
                sql_query = sql_query[:-3]
            
            sql_query = sql_query.strip()
            
            # Validate the query is a read-only statement
            read_only_commands = ['SELECT', 'PRAGMA TABLE_INFO', 'PRAGMA INDEX_LIST', 'PRAGMA TABLE_LIST', 'EXPLAIN QUERY PLAN']
            if not any(sql_query.upper().startswith(cmd) for cmd in read_only_commands):
                raise ValueError("Generated query is not a read-only statement")
            
            # Check for forbidden keywords
            forbidden_keywords = ['INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER', 'TRUNCATE', 'REPLACE']
            query_upper = sql_query.upper()
            if any(keyword in query_upper for keyword in forbidden_keywords):
                raise ValueError("Generated query contains forbidden SQL operations")
            
            self.logger.info(f"Generated SQL query for '{natural_language_query}': {sql_query}")
            
            return {
                'sql_query': sql_query,
                'explanation': f"Converted: '{natural_language_query}' → SQL query",
                'success': True
            }
            
        except Exception as e:
            self.logger.error(f"Error generating SQL query: {str(e)}")
            return {
                'sql_query': '',
                'explanation': f"Error: {str(e)}",
                'success': False
            }