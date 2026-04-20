from typing import List, Tuple, Optional
from ..llm import BaseLLM
from . import BaseRerank, RerankSettings


class LLMRerank(BaseRerank):
    def __init__(self, settings: RerankSettings, llm: BaseLLM):
        super().__init__(settings)
        self.llm = llm

    def rerank(self, query: str, documents: List[str], top_k: Optional[int] = None) -> List[Tuple[str, float]]:
        if not documents:
            return []

        k = top_k or self.settings.top_k
        if len(documents) <= k:
            return [(doc, 1.0) for doc in documents]

        # Create ranking prompt
        prompt = f"""Given the query: "{query}"

Rank the following documents by their relevance to the query. Return only the indices of the top {k} most relevant documents in order, separated by commas.

Documents:
"""
        for i, doc in enumerate(documents):
            prompt += f"{i+1}. {doc[:200]}...\n"

        prompt += f"\nTop {k} indices (1-based, comma-separated):"

        try:
            response = self.llm.generate(prompt)
            # Parse response for indices
            indices = []
            for part in response.strip().split(','):
                try:
                    idx = int(part.strip()) - 1
                    if 0 <= idx < len(documents):
                        indices.append(idx)
                except ValueError:
                    continue

            # If parsing failed, return first k documents
            if not indices:
                indices = list(range(min(k, len(documents))))

            return [(documents[i], 1.0 - 0.1 * j) for j, i in enumerate(indices[:k])]
        except Exception:
            # Fallback: return first k documents
            return [(documents[i], 1.0) for i in range(min(k, len(documents)))]