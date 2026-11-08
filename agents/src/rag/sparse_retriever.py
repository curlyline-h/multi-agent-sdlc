from typing import List
from langchain_core.documents import Document
from langchain_community.retrievers import BM25Retriever

class SparseRetrieverManager:
    """
    Manages keyword-based sparse search using BM25 scoring.
    """

    def __init__(self):
        self.retriever = None

    def initialize(self, documents: List[Document]):
        """
        Creates a BM25 retriever index from the provided document chunks.
        """
        if not documents:
            raise ValueError("Cannot initialize sparse retriever with empty document list.")
        self.retriever = BM25Retriever.from_documents(documents)

    def search(self, query: str, k: int = 4) -> List[Document]:
        """
        Performs keyword match search for the query string.
        """
        if not self.retriever:
            raise ValueError("BM25 index has not been initialized.")
        self.retriever.k = k
        return self.retriever.invoke(query)

    def get_retriever(self, k: int = 4) -> BM25Retriever:
        """
        Returns the initialized BM25 retriever instance.
        """
        if not self.retriever:
            raise ValueError("BM25 index has not been initialized.")
        self.retriever.k = k
        return self.retriever
