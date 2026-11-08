from typing import List, Optional
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_huggingface import HuggingFaceEmbeddings

# Import modular pipeline components
from agents.src.rag.document_processor import DocumentProcessor
from agents.src.rag.vector_store import VectorStoreManager
from agents.src.rag.sparse_retriever import SparseRetrieverManager
from agents.src.rag.hybrid_retriever import HybridRetrieverManager

# ---------------------------------------------------------------------------
# Cached embeddings instance (loaded once, reused across calls)
# ---------------------------------------------------------------------------
_embeddings_instance: Optional[HuggingFaceEmbeddings] = None


def _get_embeddings() -> HuggingFaceEmbeddings:
    global _embeddings_instance
    if _embeddings_instance is None:
        _embeddings_instance = HuggingFaceEmbeddings(
            model_name="all-MiniLM-L6-v2",
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
    return _embeddings_instance


class RAGPipeline:
    """
    Orchestrator that ties together document extraction, chunking,
    vector storage, sparse indexing, and hybrid retrieval.
    """

    def __init__(
        self,
        persist_directory: str = "./chroma_db",
        embeddings: Optional[Embeddings] = None
    ):
        self.embeddings = embeddings or _get_embeddings()
        self.vector_store_manager = VectorStoreManager(persist_directory, self.embeddings)
        self.sparse_retriever_manager = SparseRetrieverManager()
        self.hybrid_retriever_manager = HybridRetrieverManager()

        # If Chroma database already exists on disk, restore BM25 and Hybrid retriever
        if self.vector_store_manager.vectorstore is not None:
            try:
                db_data = self.vector_store_manager.vectorstore.get()
                documents = []
                if db_data and "documents" in db_data:
                    metadatas = db_data.get("metadatas") or [None] * len(db_data["documents"])
                    for doc_text, metadata in zip(db_data["documents"], metadatas):
                        documents.append(Document(page_content=doc_text, metadata=metadata or {}))
                
                if documents:
                    self.sparse_retriever_manager.initialize(documents)
                    dense_retriever = self.vector_store_manager.as_retriever(k=4)
                    sparse_retriever = self.sparse_retriever_manager.get_retriever(k=4)
                    self.hybrid_retriever_manager.initialize(dense_retriever, sparse_retriever)
            except Exception as e:
                print(f"Warning: Failed to restore BM25 and hybrid retriever: {e}")

    def ingest_directory(
        self,
        directory_path: str,
        glob_pattern: str = "**/*.*",
        chunk_size: int = 1000,
        chunk_overlap: int = 200
    ):
        """
        Runs the full ingestion cycle across components.
        """
        # 1. Extract documents
        raw_docs = DocumentProcessor.extract_documents(directory_path, glob_pattern)
        if not raw_docs:
            print(f"No documents found in directory '{directory_path}' matching pattern '{glob_pattern}'.")
            return

        # 2. Chunk text recursively
        chunks = DocumentProcessor.chunk_documents(raw_docs, chunk_size, chunk_overlap)
        print(f"Segmented {len(raw_docs)} documents into {len(chunks)} chunks.")

        # 3. Add to Chroma vector database
        self.vector_store_manager.add_documents(chunks)
        print("Populated dense vector store.")

        # 4. Initialize BM25 search index
        self.sparse_retriever_manager.initialize(chunks)
        print("Initialized sparse keyword index.")

        # 5. Connect retrievers in an ensemble hybrid layout
        dense_retriever = self.vector_store_manager.as_retriever(k=4)
        sparse_retriever = self.sparse_retriever_manager.get_retriever(k=4)
        self.hybrid_retriever_manager.initialize(dense_retriever, sparse_retriever)
        print("Hybrid search integration ready.")

    def hybrid_search(self, query: str, k: int = 4) -> List[Document]:
        """
        Ensemble retrieval merging vector scores and keyword rank.
        """
        if not self.hybrid_retriever_manager.dense_retriever or not self.hybrid_retriever_manager.sparse_retriever:
            # Fallback if hybrid/BM25 is not initialized but we have a vector store
            if self.vector_store_manager.vectorstore is not None:
                try:
                    return self.vector_store_manager.similarity_search(query, k=k)
                except Exception:
                    pass
            return []
        return self.hybrid_retriever_manager.search(query, k=k)
