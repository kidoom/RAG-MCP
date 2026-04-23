"""Factory for creating evaluator instances."""

from __future__ import annotations

from typing import Dict, Type

from .base_evaluator import BaseEvaluator, EvaluatorSettings
from .custom_evaluator import CustomEvaluator


class EvaluatorFactory:
    """Factory class for evaluator providers."""

    _providers: Dict[str, Type[BaseEvaluator]] = {
        "custom": CustomEvaluator,
    }

    @classmethod
    def create(cls, settings: EvaluatorSettings) -> BaseEvaluator:
        """Create an evaluator instance based on configured provider."""
        provider_name = settings.provider.lower()
        provider_cls = cls._providers.get(provider_name)

        if not provider_cls:
            available = ", ".join(sorted(cls._providers.keys())) or "none"
            raise ValueError(
                f"Unsupported evaluator provider: {provider_name}. "
                f"Available providers: {available}"
            )

        return provider_cls(settings)

    @classmethod
    def register_provider(cls, name: str, provider_cls: Type[BaseEvaluator]) -> None:
        """Register an evaluator provider implementation."""
        cls._providers[name.lower()] = provider_cls

    @classmethod
    def list_providers(cls) -> list[str]:
        """List all available evaluator providers."""
        return sorted(cls._providers.keys())
