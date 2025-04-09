from typing import Any, Dict, List, Callable
from .logger import setup_logger

class ToolManager:
    """Manages tool registration and execution"""
    
    def __init__(self, logger=None):
        """
        Initialize ToolManager
        
        Args:
            logger: Logger instance (optional)
        """
        self._tools = {}
        self._name_mapping = {}  # Maps normalized names to original names
        self.logger = logger or setup_logger(__name__)
        self.logger.info("ToolManager initialized")
    
    def _normalize_name(self, name: str) -> str:
        """Convert hyphenated names to underscore format"""
        return name.replace('-', '_')
    
    def register_tool(self, name: str, func: Callable, description: str, input_schema: Dict):
        """
        Register a new tool
        
        Args:
            name: Tool name
            func: Tool execution function
            description: Tool description
            input_schema: Tool input schema
        """
        normalized_name = self._normalize_name(name)
        self._name_mapping[normalized_name] = name
        self._tools[normalized_name] = {
            'function': func,
            'description': description,
            'input_schema': input_schema,
            'original_name': name
        }
        self.logger.info(f"Registered tool: {name}")

    def get_tools(self) -> Dict[str, List[Dict]]:
        """
        Generate tool specifications in Bedrock format
        
        Returns:
            Dict: Tool specifications dictionary
        """
        tool_specs = []
        for normalized_name, tool in self._tools.items():
            tool_specs.append({
                "toolSpec": {
                    "name": normalized_name,
                    "description": tool['description'],
                    "inputSchema": {
                        "json": tool['input_schema']
                    }
                }
            })
        
        return {"tools": tool_specs}

    async def execute_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> Any:
        """
        Execute a tool based on agent request
        
        Args:
            tool_name: Tool name
            tool_input: Tool input parameters
            
        Returns:
            Any: Tool execution result
            
        Raises:
            ValueError: If tool not found or execution fails
        """
        normalized_name = self._normalize_name(tool_name)
        
        if normalized_name not in self._tools:
            self.logger.error(f"Unknown tool: {normalized_name}")
            raise ValueError(f"Unknown tool: {normalized_name}")
        
        try:
            tool_func = self._tools[normalized_name]['function']
            original_name = self._tools[normalized_name]['original_name']
            result = await tool_func(original_name, tool_input)
            self.logger.debug("Tool execution successful")
            return result
        except Exception as e:
            self.logger.error(f"Tool execution error: {e}", exc_info=True)
            raise ValueError(f"Tool execution error: {str(e)}")

    def clear_tools(self):
        """Clear all registered tools"""
        tool_count = len(self._tools)
        self._tools.clear()
        self._name_mapping.clear()
        self.logger.info(f"Cleared {tool_count} tools")
