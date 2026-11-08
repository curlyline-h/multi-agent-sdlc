from typing import List, Optional
from collections import defaultdict
from langchain_core.documents import Document

class HybridRetrieverManager:
    """
    Manages hybrid search by combining dense semantic retrievers and sparse keyword retrievers
    using Reciprocal Rank Fusion (RRF).

    Replaces the deprecated langchain_community.retrievers.EnsembleRetriever
    with a simple inline implementation of the same RRF algorithm.
    """

    def __init__(self):
        self.dense_retriever = None
        self.sparse_retriever = None
        self.weights: List[float] = [0.5, 0.5]

    def initialize(
        self,
        dense_retriever,
        sparse_retriever,
        weights: Optional[List[float]] = None,
    ):
        """
        Stores both retrievers and weight distributions for RRF fusion.
        """
        self.dense_retriever = dense_retriever
        self.sparse_retriever = sparse_retriever
        self.weights = weights or [0.5, 0.5]

    def search(self, query: str, k: int = 4) -> List[Document]:
        """
        Runs RRF hybrid retrieval: fetches from both retrievers, fuses
        scores using Reciprocal Rank Fusion, and returns the top-k results.
        """
        if not self.dense_retriever or not self.sparse_retriever:
            raise ValueError("Hybrid retriever has not been initialized.")

        # Fetch results from both retrievers
        dense_docs = self.dense_retriever.invoke(query)
        sparse_docs = self.sparse_retriever.invoke(query)

        # RRF scoring: score = weight * (1 / (rank + 60))
        rrf_constant = 60  # Standard RRF constant
        scores: dict[str, float] = defaultdict(float)
        doc_map: dict[str, Document] = {}

        for rank, doc in enumerate(dense_docs):
            doc_key = doc.page_content
            scores[doc_key] += self.weights[0] * (1.0 / (rank + rrf_constant))
            doc_map[doc_key] = doc

        for rank, doc in enumerate(sparse_docs):
            doc_key = doc.page_content
            scores[doc_key] += self.weights[1] * (1.0 / (rank + rrf_constant))
            doc_map[doc_key] = doc

        # Sort by fused score descending, return top-k
        sorted_keys = sorted(scores, key=scores.get, reverse=True)[:k]
        return [doc_map[key] for key in sorted_keys]

