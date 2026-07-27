import os
import time
import requests
import structlog
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

logger = structlog.get_logger()

class BaseLLMProvider(ABC):
    @abstractmethod
    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        run_id: Optional[str] = None
    ) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        pass

class GroqProvider(BaseLLMProvider):
    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 3
    ):
        self.api_key = api_key or os.environ.get("groq1") or os.environ.get("GROQ_API_KEY") or os.environ.get("groq")
        self.model = model or os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
        self.timeout = timeout
        self.max_retries = max_retries
        self.url = "https://api.groq.com/openai/v1/chat/completions"

    def get_model_name(self) -> str:
        return self.model

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        run_id: Optional[str] = None
    ) -> Dict[str, Any]:
        from app.services.ai.advisor.advisor_exceptions import GroqAPIException

        if not self.api_key:
            raise GroqAPIException("Groq API key is missing. Please set GROQ_API_KEY in the environment or .env file.")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": temperature,
            "response_format": {"type": "json_object"}
        }

        attempts = 0
        backoff = 1.0
        last_error = ""

        log = logger.bind(
            run_id=run_id,
            model=self.model,
            temperature=temperature,
            provider="groq"
        )

        while attempts <= self.max_retries:
            log.info("groq_request_started", attempt=attempts)
            t0 = time.perf_counter()
            try:
                response = requests.post(self.url, headers=headers, json=data, timeout=self.timeout)
                latency_ms = (time.perf_counter() - t0) * 1000
                
                # Check for transient errors
                if response.status_code in [429, 500, 502, 503, 504]:
                    last_error = f"HTTP {response.status_code}: {response.text}"
                    log.warning("groq_request_transient_error", error=last_error, status_code=response.status_code)
                    attempts += 1
                    if attempts <= self.max_retries:
                        time.sleep(backoff)
                        backoff *= 2.0
                    continue
                
                # Permanent error
                if response.status_code != 200:
                    log.error("groq_request_permanent_error", status_code=response.status_code, text=response.text[:500])
                    raise GroqAPIException(f"Groq API returned permanent error {response.status_code}: {response.text[:500]}")

                # Success
                log.info("groq_request_finished", latency_ms=round(latency_ms, 2))
                res_json = response.json()
                content = res_json["choices"][0]["message"]["content"]
                
                try:
                    import json
                    return json.loads(content)
                except Exception as je:
                    log.error("groq_response_json_parse_failed", error=str(je))
                    raise GroqAPIException(f"Failed to parse Groq response content as JSON: {str(je)}")

            except requests.exceptions.RequestException as re:
                last_error = str(re)
                log.warning("groq_request_network_error", error=last_error)
                attempts += 1
                if attempts <= self.max_retries:
                    time.sleep(backoff)
                    backoff *= 2.0
                continue

        log.error("groq_request_retries_exhausted", error=last_error)
        raise GroqAPIException(f"Groq API call failed after {self.max_retries} retries. Last error: {last_error}")
