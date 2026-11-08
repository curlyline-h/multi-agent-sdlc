import os
from typing import List, Optional
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_community.vectorstores import Chroma

class VectorStoreManager:
    """
    Manages loading, populating, and searching a local Chroma DB vector store.
    """

    def __init__(self, persist_directory: str, embeddings: Embeddings):
        self.persist_directory = persist_directory
        self.embeddings = embeddings
        self.vectorstore = None
        self.load_store()

    def load_store(self):
        """
        Loads the database if the persist directory exists on disk.
        """
        if os.path.exists(self.persist_directory):
            self.vectorstore = Chroma(
                persist_directory=self.persist_directory,
                embedding_function=self.embeddings
            )

    def add_documents(self, documents: List[Document]):
        """
        Populates Chroma database with documents and persists changes.
        """
        self.vectorstore = Chroma.from_documents(
            documents=documents,
            embedding=self.embeddings,
            persist_directory=self.persist_directory
        )

    def similarity_search(self, query: str, k: int = 4) -> List[Document]:
        """
        Performs dense vector similarity search.
        """
        if not self.vectorstore:
            raise ValueError("Chroma Vector store is not initialized or populated.")
        return self.vectorstore.similarity_search(query, k=k)

    def as_retriever(self, k: int = 4):
        """
        Converts the vector store to a standard LangChain retriever object.
        """
        if not self.vectorstore:
            raise ValueError("Chroma Vector store is not initialized or populated.")
        return self.vectorstore.as_retriever(search_kwargs={"k": k})
