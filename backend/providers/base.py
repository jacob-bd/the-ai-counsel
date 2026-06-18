"""Base class for LLM providers."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any

class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def query(self, model_id: str, messages: List[Dict[str, str]], timeout: float = 120.0, temperature: float = 0.7) -> Dict[str, Any]:
        """
        Send a query to the LLM.
        
        Args:
            model_id: The ID of the model to query.
            messages: List of message dicts (role, content).
            timeout: Request timeout in seconds.
            
        Returns:
            Dict containing 'content' (str) or 'error' (bool) and 'error_message' (str).
        """
        pass

    @abstractmethod
    async def get_models(self) -> List[Dict[str, Any]]:
        """
        Fetch available models from the provider.
        
        Returns:
            List of model dicts (id, name, context_length, etc.).
        """
        pass

    @abstractmethod
    async def validate_key(self, api_key: str) -> Dict[str, Any]:
        """
        Validate the provided API key.
        
        Args:
            api_key: The API key to test.
            
        Returns:
            Dict with 'success' (bool) and 'message' (str).
        """
        pass
