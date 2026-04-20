from typing import List, Tuple, Optional
from . import BaseRerank, RerankSettings


class CrossEncoderRerank(BaseRerank):
    def __init__(self, settings: RerankSettings):
        super().__init__(settings)
        try:
            from sentence_transformers import CrossEncoder
            self.model = CrossEncoder(settings.model)
        except ImportError:
            raise ImportError("sentence-transformers is required for CrossEncoder reranking. Install with: pip install sentence-transformers")

    def rerank(self, query: str, documents: List[str], top_k: Optional[int] = None) -> List[Tuple[str, float]]:
        if not documents:
            return []

        k = top_k or self.settings.top_k

        # Compute scores
        pairs = [[query, doc] for doc in documents]
        scores = self.model.predict(pairs)

        # Sort by score descending
        scored_docs = list(zip(documents, scores))
        scored_docs.sort(key=lambda x: x[1], reverse=True)

        return scored_docs[:k]