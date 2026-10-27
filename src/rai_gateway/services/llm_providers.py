"""LLM provider abstraction for RAI Gateway.

Supports all major LLM providers:
- OpenAI (GPT-4, GPT-3.5)
- Azure OpenAI
- Anthropic (Claude)
- AWS Bedrock
- Google Vertex AI
- Ollama (local/on-prem)
"""

import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import httpx

from rai_gateway.core.config import settings


class LLMProviderBase(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def generate(
        self, prompt: str, variables: Dict[str, Any], model: str, **kwargs
    ) -> Dict[str, Any]:
        """Generate LLM response with provider-agnostic interface.

        Args:
            prompt: Template prompt string
            variables: Variables to fill in prompt
            model: Model identifier (provider-specific)
            **kwargs: Provider-specific generation params

        Returns:
            Dict with keys: output, model, usage, provider
        """
        pass

    async def list_models(self) -> Dict[str, Any]:
        """Return available models for provider.

        Returns a payload with:
        - provider: provider name
        - models: list[str]
        - source: live|fallback
        """
        return {
            "provider": "unknown",
            "models": [],
            "source": "fallback",
        }


class OpenAIProvider(LLMProviderBase):
    """OpenAI LLM provider implementation."""

    def __init__(self, api_key: Optional[str] = None, endpoint: Optional[str] = None):
        self.api_key = (
            api_key
            or settings.llm_provider_api_key
            or os.environ.get("LLM_PROVIDER_API_KEY")
        )
        self.endpoint = (
            endpoint
            or settings.llm_provider_url
            or os.environ.get("LLM_PROVIDER_URL", "https://api.openai.com/v1")
        )

    async def generate(
        self, prompt: str, variables: Dict[str, Any], model: str, **kwargs
    ) -> Dict[str, Any]:
        # Simple template fill
        prompt_filled = prompt.format(**variables)
        url = f"{self.endpoint}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt_filled}],
            "max_tokens": kwargs.get("max_tokens", 256),
            "temperature": kwargs.get("temperature", 0.7),
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        return {
            "output": data["choices"][0]["message"]["content"],
            "model": data.get("model", model),
            "usage": data.get("usage", {}),
            "provider": "openai",
        }

    async def list_models(self) -> Dict[str, Any]:
        fallback_models = [
            "gpt-4.1",
            "gpt-4o",
            "gpt-4o-mini",
            "o3-mini",
        ]
        if not self.api_key:
            return {
                "provider": "openai",
                "models": fallback_models,
                "source": "fallback",
            }

        url = f"{self.endpoint}/models"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            models = [
                item.get("id", "") for item in data.get("data", []) if item.get("id")
            ]
            # Keep chat-capable modern families only for admin UX clarity.
            filtered = sorted(
                [m for m in models if m.startswith("gpt-") or m.startswith("o")],
                reverse=True,
            )
            return {
                "provider": "openai",
                "models": filtered or fallback_models,
                "source": "live" if filtered else "fallback",
            }
        except Exception:
            return {
                "provider": "openai",
                "models": fallback_models,
                "source": "fallback",
            }


# Provider registry and selector
def get_llm_provider(provider_name: str = "openai") -> LLMProviderBase:
    """Get LLM provider instance by name.

    Args:
        provider_name: One of: openai, azure_openai, anthropic, bedrock, vertex, ollama

    Returns:
        LLMProviderBase instance
    """
    providers = {
        "openai": OpenAIProvider,
        "azure_openai": AzureOpenAIProvider,
        "anthropic": AnthropicProvider,
        "bedrock": BedrockProvider,
        "vertex": VertexProvider,
        "ollama": OllamaProvider,
    }

    provider_class = providers.get(provider_name.lower())
    if not provider_class:
        raise NotImplementedError(
            f"Provider '{provider_name}' not supported. "
            f"Available: {', '.join(providers.keys())}"
        )

    return provider_class()


class AzureOpenAIProvider(LLMProviderBase):
    """Azure OpenAI provider (enterprise deployments)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        deployment: Optional[str] = None,
    ):
        self.api_key = (
            api_key
            or settings.azure_openai_api_key
            or os.environ.get("AZURE_OPENAI_API_KEY")
        )
        self.endpoint = (
            endpoint
            or settings.azure_openai_endpoint
            or os.environ.get("AZURE_OPENAI_ENDPOINT")
        )
        self.deployment = (
            deployment
            or settings.azure_openai_deployment
            or os.environ.get("AZURE_OPENAI_DEPLOYMENT")
        )
        self.api_version = settings.azure_openai_api_version or os.environ.get(
            "AZURE_OPENAI_API_VERSION", "2024-02-15-preview"
        )

    async def generate(
        self, prompt: str, variables: Dict[str, Any], model: str, **kwargs
    ) -> Dict[str, Any]:
        prompt_filled = prompt.format(**variables)
        url = f"{self.endpoint}/openai/deployments/{self.deployment or model}/chat/completions?api-version={self.api_version}"
        headers = {"api-key": self.api_key, "Content-Type": "application/json"}
        payload = {
            "messages": [{"role": "user", "content": prompt_filled}],
            "max_tokens": kwargs.get("max_tokens", 256),
            "temperature": kwargs.get("temperature", 0.7),
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        return {
            "output": data["choices"][0]["message"]["content"],
            "model": data.get("model", self.deployment or model),
            "usage": data.get("usage", {}),
            "provider": "azure_openai",
        }

    async def list_models(self) -> Dict[str, Any]:
        models: List[str] = []
        if self.deployment:
            models.append(self.deployment)
        models.extend(
            [
                "gpt-4o",
                "gpt-4o-mini",
                "gpt-4.1",
            ]
        )
        deduped = list(dict.fromkeys(models))
        return {
            "provider": "azure_openai",
            "models": deduped,
            "source": "fallback",
        }


class AnthropicProvider(LLMProviderBase):
    """Anthropic Claude provider."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = (
            api_key or settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
        )
        self.endpoint = "https://api.anthropic.com/v1"

    async def generate(
        self, prompt: str, variables: Dict[str, Any], model: str, **kwargs
    ) -> Dict[str, Any]:
        prompt_filled = prompt.format(**variables)
        url = f"{self.endpoint}/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model or "claude-3-5-sonnet-20241022",
            "messages": [{"role": "user", "content": prompt_filled}],
            "max_tokens": kwargs.get("max_tokens", 1024),
            "temperature": kwargs.get("temperature", 0.7),
        }
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        return {
            "output": data["content"][0]["text"],
            "model": data.get("model", model),
            "usage": data.get("usage", {}),
            "provider": "anthropic",
        }

    async def list_models(self) -> Dict[str, Any]:
        # Anthropic model listing APIs vary by account/features; keep curated defaults.
        return {
            "provider": "anthropic",
            "models": [
                "claude-3-5-sonnet-20241022",
                "claude-3-5-haiku-20241022",
                "claude-3-opus-20240229",
            ],
            "source": "fallback",
        }


class BedrockProvider(LLMProviderBase):
    """AWS Bedrock provider (requires boto3)."""

    def __init__(self, region: Optional[str] = None):
        self.region = (
            region or settings.aws_region or os.environ.get("AWS_REGION", "us-east-1")
        )
        self._client = None

    async def generate(
        self, prompt: str, variables: Dict[str, Any], model: str, **kwargs
    ) -> Dict[str, Any]:
        prompt_filled = prompt.format(**variables)

        try:
            import json

            import boto3

            if not self._client:
                self._client = boto3.client("bedrock-runtime", region_name=self.region)

            # Model-specific payload formatting
            if "anthropic.claude" in model:
                body = json.dumps(
                    {
                        "anthropic_version": "bedrock-2023-05-31",
                        "messages": [{"role": "user", "content": prompt_filled}],
                        "max_tokens": kwargs.get("max_tokens", 1024),
                        "temperature": kwargs.get("temperature", 0.7),
                    }
                )
            elif "amazon.titan" in model:
                body = json.dumps(
                    {
                        "inputText": prompt_filled,
                        "textGenerationConfig": {
                            "maxTokenCount": kwargs.get("max_tokens", 1024),
                            "temperature": kwargs.get("temperature", 0.7),
                        },
                    }
                )
            else:
                raise ValueError(f"Unsupported Bedrock model: {model}")

            response = self._client.invoke_model(modelId=model, body=body)

            result = json.loads(response["body"].read())

            # Parse response based on model
            if "anthropic.claude" in model:
                output = result["content"][0]["text"]
            elif "amazon.titan" in model:
                output = result["results"][0]["outputText"]
            else:
                output = str(result)

            return {
                "output": output,
                "model": model,
                "usage": result.get("usage", {}),
                "provider": "bedrock",
            }

        except ImportError:
            raise RuntimeError(
                "boto3 required for Bedrock provider. Install: pip install boto3"
            )

    async def list_models(self) -> Dict[str, Any]:
        fallback = [
            "anthropic.claude-3-sonnet-20240229-v1:0",
            "anthropic.claude-3-haiku-20240307-v1:0",
            "amazon.titan-text-express-v1",
        ]
        try:
            import boto3

            client = boto3.client("bedrock", region_name=self.region)
            response = client.list_foundation_models()
            models = [
                item.get("modelId", "")
                for item in response.get("modelSummaries", [])
                if item.get("modelId")
            ]
            return {
                "provider": "bedrock",
                "models": sorted(models) or fallback,
                "source": "live" if models else "fallback",
            }
        except Exception:
            return {"provider": "bedrock", "models": fallback, "source": "fallback"}


class VertexProvider(LLMProviderBase):
    """Google Vertex AI provider (requires google-cloud-aiplatform)."""

    def __init__(
        self, project_id: Optional[str] = None, location: Optional[str] = None
    ):
        self.project_id = (
            project_id or settings.gcp_project_id or os.environ.get("GCP_PROJECT_ID")
        )
        self.location = (
            location
            or settings.gcp_location
            or os.environ.get("GCP_LOCATION", "us-central1")
        )

    async def generate(
        self, prompt: str, variables: Dict[str, Any], model: str, **kwargs
    ) -> Dict[str, Any]:
        prompt_filled = prompt.format(**variables)

        try:
            from google.cloud import aiplatform
            from vertexai.language_models import TextGenerationModel

            aiplatform.init(project=self.project_id, location=self.location)

            model_instance = TextGenerationModel.from_pretrained(
                model or "text-bison@002"
            )
            response = model_instance.predict(
                prompt_filled,
                max_output_tokens=kwargs.get("max_tokens", 1024),
                temperature=kwargs.get("temperature", 0.7),
            )

            return {
                "output": response.text,
                "model": model,
                "usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                },  # Vertex doesn't expose this easily
                "provider": "vertex",
            }

        except ImportError:
            raise RuntimeError(
                "google-cloud-aiplatform required for Vertex. Install: pip install google-cloud-aiplatform"
            )

    async def list_models(self) -> Dict[str, Any]:
        return {
            "provider": "vertex",
            "models": [
                "gemini-1.5-pro-001",
                "gemini-1.5-flash-001",
                "gemini-2.0-flash-001",
            ],
            "source": "fallback",
        }


class OllamaProvider(LLMProviderBase):
    """Ollama provider for local/on-prem LLMs."""

    def __init__(self, endpoint: Optional[str] = None):
        self.endpoint = (
            endpoint
            or settings.ollama_endpoint
            or os.environ.get("OLLAMA_ENDPOINT", "http://localhost:11434")
        )

    async def generate(
        self, prompt: str, variables: Dict[str, Any], model: str, **kwargs
    ) -> Dict[str, Any]:
        prompt_filled = prompt.format(**variables)
        url = f"{self.endpoint}/api/generate"
        payload = {
            "model": model or "llama2",
            "prompt": prompt_filled,
            "stream": False,
            "options": {
                "temperature": kwargs.get("temperature", 0.7),
                "num_predict": kwargs.get("max_tokens", 256),
            },
        }

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        return {
            "output": data.get("response", ""),
            "model": data.get("model", model),
            "usage": {
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
            },
            "provider": "ollama",
        }

    async def list_models(self) -> Dict[str, Any]:
        fallback = ["llama3", "mistral", "qwen2.5"]
        try:
            url = f"{self.endpoint}/api/tags"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
            models = [
                item.get("name", "")
                for item in data.get("models", [])
                if item.get("name")
            ]
            return {
                "provider": "ollama",
                "models": models or fallback,
                "source": "live" if models else "fallback",
            }
        except Exception:
            return {"provider": "ollama", "models": fallback, "source": "fallback"}


async def list_provider_models(provider_name: str) -> Dict[str, Any]:
    """List models for provider; use live fetch when supported."""
    if provider_name == "auto":
        models: List[str] = []
        if settings.llm_provider_api_key:
            models.append(settings.llm_provider_model)
        if settings.anthropic_api_key:
            models.append("claude-3-5-sonnet-20241022")
        if settings.azure_openai_deployment:
            models.append(settings.azure_openai_deployment)
        if settings.gcp_project_id:
            models.append("gemini-1.5-pro-001")
        if settings.aws_region:
            models.append("anthropic.claude-3-sonnet-20240229-v1:0")
        if settings.ollama_endpoint:
            models.append("llama3")
        deduped = list(dict.fromkeys([m for m in models if m]))
        return {
            "provider": "auto",
            "models": deduped,
            "source": "fallback",
        }

    provider = get_llm_provider(provider_name)
    return await provider.list_models()
