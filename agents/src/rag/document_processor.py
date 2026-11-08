import os
import glob
from typing import List
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import TextLoader, PyPDFLoader

class DocumentProcessor:
    """
    Handles text extraction from local directories and recursive text chunking.
    Supports .txt, .md, and .pdf files.
    """

    @staticmethod
    def extract_documents(directory_path: str, glob_pattern: str = "**/*.*") -> List[Document]:
        """
        Loads all raw text, markdown, or PDF files matching the glob pattern recursively.
        """
        if not os.path.exists(directory_path):
            raise FileNotFoundError(f"Source directory '{directory_path}' does not exist.")
            
        documents = []
        search_path = os.path.join(directory_path, glob_pattern)
        file_paths = glob.glob(search_path, recursive=True)
        
        for file_path in file_paths:
            if not os.path.isfile(file_path):
                continue
                
            ext = os.path.splitext(file_path)[1].lower()
            try:
                if ext == ".pdf":
                    loader = PyPDFLoader(file_path)
                    documents.extend(loader.load())
                elif ext in [".txt", ".md"]:
                    loader = TextLoader(file_path, encoding="utf-8")
                    documents.extend(loader.load())
            except Exception as e:
                print(f"Warning: Failed to load file '{file_path}': {e}")
                
        return documents

    @staticmethod
    def chunk_documents(
        documents: List[Document], 
        chunk_size: int = 1000, 
        chunk_overlap: int = 200
    ) -> List[Document]:
        """
        Splits loaded documents recursively based on structure boundaries.
        """
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", " ", ""]
        )
        return splitter.split_documents(documents)
