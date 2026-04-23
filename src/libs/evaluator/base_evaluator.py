"""Base abstractions for evaluator implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class EvaluatorSettings:
    """Configuration for evaluator providers."""

    provider: str
    top_k: int = 10
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvaluationInput:
    """Input payload for evaluation."""

    query: str
    retrieved_ids: List[str]
    golden_ids: List[str]
    generated_answer: Optional[str] = None
    ground_truth: Optional[str] = None


class BaseEvaluator(ABC):
    """Abstract base class for all evaluator providers."""

    def __init__(self, settings: EvaluatorSettings):
        self.settings = settings

    @abstractmethod
    def evaluate(
        self,
        payload: EvaluationInput,
        trace: Optional[Any] = None,
    ) -> Dict[str, float]:
        """Evaluate retrieval/generation quality and return normalized metrics."""
        raise NotImplementedError
