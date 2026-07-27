import os
import structlog
from typing import Any, Dict, Optional
from app.services.ai.advisor.llm_providers import BaseLLMProvider, GroqProvider

logger = structlog.get_logger()

class AdvisorService:
    def __init__(self, provider: Optional[BaseLLMProvider] = None, model: Optional[str] = None, api_key: Optional[str] = None):
        if provider:
            self.provider = provider
        else:
            self.provider = GroqProvider(model=model, api_key=api_key)

    @property
    def model(self) -> str:
        return self.provider.get_model_name()

    def call_groq(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        run_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Delegates LLM generation to the configured BaseLLMProvider."""
        return self.provider.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            run_id=run_id
        )
