import json
import time
import asyncio
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
import httpx

from vartalap.settings import get_settings, LLMConfig
from vartalap.logger import log_llm_call


def clean_json_response(raw_text: str) -> Dict[str, Any]:
    """Cleans markdown code fences and parses JSON from raw LLM output."""
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # Remove opening ``` or ```json
        if lines[0].startswith("```"):
            lines = lines[1:]
        # Remove closing ```
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Fallback: extract substring between first { and last }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            json_substr = text[start : end + 1]
            return json.loads(json_substr)
        raise ValueError(f"Failed to parse valid JSON from LLM output:\n{raw_text}")


class LLMProvider(ABC):
    """Abstract interface for backend-agnostic LLM providers."""

    @abstractmethod
    async def generate(self, prompt: str, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Generate response from LLM given prompt and json schema expectation."""
        pass


class CLILLMProvider(LLMProvider):
    """CLI sub-process provider (e.g. antigravity -p '{prompt}')."""

    def __init__(self, command_template: str, timeout_seconds: int = 60):
        self.command_template = command_template
        self.timeout_seconds = timeout_seconds

    async def generate(self, prompt: str, schema: Dict[str, Any]) -> Dict[str, Any]:
        start_time = time.time()
        # Escaping quotes in prompt for safe shell injection if needed, or format
        # Format command template replacing {prompt}
        # Escape double quotes or pass prompt via stdin/arg
        cmd_str = self.command_template.replace("{prompt}", f'"{prompt}"')
        
        print(f"[LLM:CLI] Executing command: {cmd_str[:80]}...")
        
        proc = await asyncio.create_subprocess_shell(
            cmd_str,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self.timeout_seconds
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise TimeoutError(f"CLI command timed out after {self.timeout_seconds}s")

        raw_output = stdout.decode("utf-8", errors="replace").strip()
        duration_ms = int((time.time() - start_time) * 1000)

        log_llm_call(
            backend="cli",
            prompt=prompt,
            response=raw_output,
            duration_ms=duration_ms
        )

        if proc.returncode != 0:
            err_msg = stderr.decode("utf-8", errors="replace")
            print(f"[LLM:CLI] CLI exited with code {proc.returncode}: {err_msg}")
            # If stdout has content, try parsing, else raise
            if not raw_output:
                raise RuntimeError(f"CLI failed (code {proc.returncode}): {err_msg}")

        return clean_json_response(raw_output)


class OllamaCloudLLMProvider(LLMProvider):
    """Ollama Cloud API provider."""

    def __init__(self, endpoint: str, model: str, api_key: Optional[str] = None):
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.api_key = api_key

    async def generate(self, prompt: str, schema: Dict[str, Any]) -> Dict[str, Any]:
        start_time = time.time()
        url = f"{self.endpoint}/chat" if not self.endpoint.endswith("/chat") else self.endpoint
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": "json"
        }

        print(f"[LLM:OLLAMA_CLOUD] Calling endpoint: {url} with model: {self.model}")
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            res_data = resp.json()

        raw_text = res_data.get("message", {}).get("content", "") or res_data.get("response", "")
        duration_ms = int((time.time() - start_time) * 1000)

        log_llm_call(
            backend="ollama_cloud",
            prompt=prompt,
            response=raw_text,
            duration_ms=duration_ms
        )

        return clean_json_response(raw_text)


class APILLMProvider(LLMProvider):
    """Standard hosted LLM API (OpenAI/Anthropic compatible)."""

    def __init__(self, provider: str, model: str, api_key: Optional[str] = None):
        self.provider = provider.lower()
        self.model = model
        self.api_key = api_key

    async def generate(self, prompt: str, schema: Dict[str, Any]) -> Dict[str, Any]:
        start_time = time.time()
        headers = {"Content-Type": "application/json"}

        if self.provider == "anthropic":
            url = "https://api.anthropic.com/v1/messages"
            headers["x-api-key"] = self.api_key or ""
            headers["anthropic-version"] = "2023-06-01"
            payload = {
                "model": self.model,
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": prompt}]
            }
        else:  # openai default
            url = "https://api.openai.com/v1/chat/completions"
            headers["Authorization"] = f"Bearer {self.api_key or ''}"
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"}
            }

        print(f"[LLM:API] Calling {self.provider} API with model: {self.model}")
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            res_data = resp.json()

        if self.provider == "anthropic":
            raw_text = res_data["content"][0]["text"]
        else:
            raw_text = res_data["choices"][0]["message"]["content"]

        duration_ms = int((time.time() - start_time) * 1000)

        log_llm_call(
            backend=f"api_{self.provider}",
            prompt=prompt,
            response=raw_text,
            duration_ms=duration_ms
        )

        return clean_json_response(raw_text)


def get_llm_provider(llm_config: Optional[LLMConfig] = None) -> LLMProvider:
    """Factory to return LLMProvider instance based on config."""
    if llm_config is None:
        llm_config = get_settings().llm

    backend = llm_config.backend.lower()
    if backend == "cli":
        return CLILLMProvider(
            command_template=llm_config.cli.command,
            timeout_seconds=llm_config.cli.timeout_seconds
        )
    elif backend == "ollama_cloud":
        return OllamaCloudLLMProvider(
            endpoint=llm_config.ollama_cloud.endpoint,
            model=llm_config.ollama_cloud.model,
            api_key=llm_config.ollama_cloud.api_key
        )
    elif backend == "api":
        return APILLMProvider(
            provider=llm_config.api.provider,
            model=llm_config.api.model,
            api_key=llm_config.api.api_key
        )
    else:
        raise ValueError(f"Unknown LLM backend: '{backend}'")


class Planner:
    """Decision planner using configurable LLM providers."""

    def __init__(self, provider: Optional[LLMProvider] = None):
        self.provider = provider or get_llm_provider()

    async def decide_next_action(
        self,
        instruction: str,
        target_username: str,
        message_history: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Formulate system prompt and prompt LLM for JSON action decision."""

        action_schema = {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["open_thread", "reply", "done", "skip"]
                },
                "username": {"type": "string"},
                "text": {"type": "string"},
                "reason": {"type": "string"}
            },
            "required": ["action"]
        }

        system_instructions = (
            "You are an autonomous Reddit DM conversation agent acting on behalf of the account holder.\n"
            "YOUR SYSTEM GUIDELINES:\n"
            "1. Match tone from the existing message history. Keep replies short, casual, and natural.\n"
            "2. Send messages strictly via an explicit 'reply' action.\n"
            "3. Return 'done' once you have sent a reply or finished the conversation.\n"
            "4. Return 'skip' if no response is needed, or if the conversation is already up-to-date.\n"
            "5. Return EXACT JSON according to the action schema.\n\n"
            "ALLOWED ACTIONS:\n"
            "- {\"action\": \"open_thread\", \"username\": \"<user>\"} -> if thread is not open\n"
            "- {\"action\": \"reply\", \"text\": \"<reply text>\"} -> to draft and send a reply\n"
            "- {\"action\": \"done\", \"reason\": \"<explanation>\"} -> task completed\n"
            "- {\"action\": \"skip\", \"reason\": \"<explanation>\"} -> no action required\n"
        )

        history_str = json.dumps(message_history, indent=2) if message_history else "[]"

        prompt = (
            f"{system_instructions}\n"
            f"--- TASK CONTEXT ---\n"
            f"High-Level Instruction: {instruction}\n"
            f"Target Username: {target_username}\n"
            f"Message History:\n{history_str}\n\n"
            f"Output JSON Action:"
        )

        return await self.provider.generate(prompt, action_schema)
