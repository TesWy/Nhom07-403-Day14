import asyncio
import os
from typing import Any, Optional

from dotenv import load_dotenv
from openai import AsyncOpenAI


class LLMProviderAdapter:
    """
    Unified adapter for multiple LLM providers used by the judge.

    Provider selection:
    - PRIMARY_PROVIDER: default provider for the primary judge
    - JUDGE_SECONDARY_PROVIDER: default provider for the secondary judge

    Supported values:
    - openai
    - anthropic
    - gemini
    - bedrock
    """

    def __init__(self, provider_override: Optional[str] = None):
        load_dotenv()

        self.provider = (
            provider_override.strip().lower()
            if provider_override
            else os.getenv("PRIMARY_PROVIDER", "openai").strip().lower()
        )

        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.anthropic_model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        self.bedrock_model = os.getenv(
            "BEDROCK_MODEL_ID",
            os.getenv("BEDROCK_MODEL", "amazon.nova-lite-v1:0"),
        ).strip()
        self.bedrock_region = (
            os.getenv("BEDROCK_AWS_REGION", "")
            or os.getenv("AWS_REGION", "")
            or os.getenv("AWS_DEFAULT_REGION", "")
            or "us-east-1"
        ).strip()
        self.aws_profile = os.getenv("AWS_PROFILE", "").strip() or None

        self._openai_client: Optional[AsyncOpenAI] = None
        self._anthropic_client: Optional[Any] = None
        self._gemini_client: Optional[Any] = None
        self._bedrock_client: Optional[Any] = None

    def _ensure_provider_supported(self) -> None:
        supported = {"openai", "anthropic", "gemini", "bedrock"}
        if self.provider not in supported:
            raise ValueError(
                f"Unsupported provider '{self.provider}'. Use one of: {sorted(supported)}"
            )

    def _has_required_key(self) -> bool:
        if self.provider == "openai":
            return bool(os.getenv("OPENAI_API_KEY"))
        if self.provider == "anthropic":
            return bool(os.getenv("ANTHROPIC_API_KEY"))
        if self.provider == "gemini":
            return bool(os.getenv("GEMINI_API_KEY"))
        if self.provider == "bedrock":
            return True
        return False

    def _get_openai_client(self) -> AsyncOpenAI:
        if self._openai_client is None:
            self._openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        return self._openai_client

    def _get_anthropic_client(self) -> Any:
        if self._anthropic_client is None:
            try:
                from anthropic import AsyncAnthropic
            except ImportError as exc:
                raise RuntimeError(
                    "Provider 'anthropic' requires the 'anthropic' package to be installed."
                ) from exc
            self._anthropic_client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        return self._anthropic_client

    def _get_gemini_client(self) -> Any:
        if self._gemini_client is None:
            try:
                from google import genai
            except ImportError as exc:
                raise RuntimeError(
                    "Provider 'gemini' requires the 'google-genai' package to be installed."
                ) from exc
            self._gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        return self._gemini_client

    def _get_bedrock_client(self) -> Any:
        if self._bedrock_client is None:
            try:
                import boto3
            except ImportError as exc:
                raise RuntimeError(
                    "Provider 'bedrock' requires the 'boto3' package to be installed."
                ) from exc

            session_kwargs = {}
            if self.aws_profile:
                session_kwargs["profile_name"] = self.aws_profile

            session = boto3.Session(**session_kwargs)
            self._bedrock_client = session.client(
                "bedrock-runtime",
                region_name=self.bedrock_region,
            )
        return self._bedrock_client

    async def _generate_with_openai(
        self,
        prompt: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> str:
        client = self._get_openai_client()
        response = await client.chat.completions.create(
            model=self.openai_model,
            messages=[
                {"role": "system", "content": system_prompt or ""},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return (response.choices[0].message.content or "").strip()

    async def _generate_with_anthropic(
        self,
        prompt: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> str:
        client = self._get_anthropic_client()
        response = await client.messages.create(
            model=self.anthropic_model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt or "",
            messages=[{"role": "user", "content": prompt}],
        )

        text_parts = []
        for block in response.content:
            if getattr(block, "type", "") == "text":
                text_parts.append(getattr(block, "text", ""))
        return "\n".join(part for part in text_parts if part).strip()

    async def _generate_with_gemini(
        self,
        prompt: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> str:
        client = self._get_gemini_client()
        merged_prompt = prompt if not system_prompt else f"System:\n{system_prompt}\n\nUser:\n{prompt}"
        _ = temperature, max_tokens

        def _gemini_call() -> str:
            response = client.models.generate_content(
                model=self.gemini_model,
                contents=merged_prompt,
            )
            return (getattr(response, "text", "") or "").strip()

        return await asyncio.to_thread(_gemini_call)

    async def _generate_with_bedrock(
        self,
        prompt: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> str:
        client = self._get_bedrock_client()

        def _bedrock_call() -> str:
            request = {
                "modelId": self.bedrock_model,
                "messages": [
                    {
                        "role": "user",
                        "content": [{"text": prompt}],
                    }
                ],
                "inferenceConfig": {
                    "temperature": temperature,
                    "maxTokens": max_tokens,
                },
            }
            if system_prompt:
                request["system"] = [{"text": system_prompt}]

            response = client.converse(**request)
            content_blocks = (
                response.get("output", {})
                .get("message", {})
                .get("content", [])
            )
            text_parts = [
                block.get("text", "")
                for block in content_blocks
                if isinstance(block, dict) and block.get("text")
            ]
            return "\n".join(text_parts).strip()

        return await asyncio.to_thread(_bedrock_call)

    async def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 800,
    ) -> str:
        self._ensure_provider_supported()

        if self.provider != "bedrock" and not self._has_required_key():
            raise RuntimeError(
                f"Missing API key for provider '{self.provider}'. Check your .env configuration."
            )

        if self.provider == "openai":
            return await self._generate_with_openai(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        if self.provider == "anthropic":
            return await self._generate_with_anthropic(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        if self.provider == "gemini":
            return await self._generate_with_gemini(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        return await self._generate_with_bedrock(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )