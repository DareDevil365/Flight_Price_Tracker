"""
Modular Tools — RAG Engine
Generalized, reusable wrapper for local document indexing (ChromaDB)
and LLM text generation (Gemini, OpenAI, Ollama). Not specific to flights.
"""

import os
from loguru import logger

# Lazy/Safe imports
GEMINI_AVAILABLE = False
OPENAI_AVAILABLE = False
OLLAMA_AVAILABLE = False
CHROMADB_AVAILABLE = False

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    logger.warning("google-generativeai not installed. Please run: pip install google-generativeai")

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    logger.warning("openai not installed. Please run: pip install openai")

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    logger.warning("ollama not installed. Please run: pip install ollama")

try:
    import chromadb
    CHROMADB_AVAILABLE = True
except ImportError:
    logger.warning("chromadb not installed. Please run: pip install chromadb")


class SimpleTextEmbedder:
    """Fallback text embedder in case Ollama is not running."""
    def __init__(self, size=128):
        self.size = size

    def embed_text(self, text: str) -> list[float]:
        """Simple deterministic hash-based embedding fallback."""
        embedding = [0.0] * self.size
        # Generate hash-based mock weights
        for idx, char in enumerate(text[:self.size * 2]):
            pos = idx % self.size
            embedding[pos] += ord(char) * (idx + 1)
        
        # Normalize vector
        magnitude = math_norm = sum(x**2 for x in embedding) ** 0.5
        if magnitude > 0:
            embedding = [x / magnitude for x in embedding]
        return embedding


class ReusableRAGEngine:
    def __init__(self, persist_dir: str, gemini_key: str = None, openai_key: str = None, ollama_host: str = None):
        self.persist_dir = persist_dir
        
        # Load APIKeyManager if run inside Flight Finder context (dynamic/fallback import)
        self.key_manager = None
        try:
            from api_key_manager import api_key_manager
            self.key_manager = api_key_manager
        except ImportError:
            pass
        
        # Initialize Gemini
        if GEMINI_AVAILABLE and gemini_key:
            genai.configure(api_key=gemini_key)
            self.gemini_client = genai.GenerativeModel("gemini-1.5-flash")
        else:
            self.gemini_client = None

        # Initialize OpenAI
        if OPENAI_AVAILABLE and openai_key:
            self.openai_client = OpenAI(api_key=openai_key)
        else:
            self.openai_client = None

        # Initialize Ollama
        if OLLAMA_AVAILABLE:
            self.ollama_client = ollama.Client(host=ollama_host or "http://localhost:11434")
        else:
            self.ollama_client = None

        # Initialize ChromaDB
        if CHROMADB_AVAILABLE:
            os.makedirs(self.persist_dir, exist_ok=True)
            self.chroma_client = chromadb.PersistentClient(path=self.persist_dir)
        else:
            self.chroma_client = None

        self.fallback_embedder = SimpleTextEmbedder()

    # ═══════════════════════════════════════════════
    # CHROMADB INDEXING & QUERYING
    # ═══════════════════════════════════════════════

    def index_documents(self, collection_name: str, documents: list[dict]):
        """
        Indexes list of documents to a local ChromaDB collection.
        `documents` is a list of dicts with keys: 'id' (str), 'text' (str), and optional 'metadata' (dict).
        """
        if not CHROMADB_AVAILABLE or not self.chroma_client:
            logger.warning("ChromaDB is unavailable. Skipping document indexing.")
            return

        try:
            collection = self.chroma_client.get_or_create_collection(name=collection_name)
            
            ids = []
            texts = []
            metadatas = []
            embeddings = []

            for doc in documents:
                doc_id = doc.get("id")
                doc_text = doc.get("text", "")
                doc_meta = doc.get("metadata", {})
                
                if not doc_id or not doc_text:
                    continue

                ids.append(doc_id)
                texts.append(doc_text)
                metadatas.append(doc_meta)
                
                # Fetch embeddings via local Ollama, fallback if unavailable
                embedding = self._get_embedding(doc_text)
                embeddings.append(embedding)

            if ids:
                collection.upsert(
                    ids=ids,
                    documents=texts,
                    metadatas=metadatas,
                    embeddings=embeddings
                )
                logger.info(f"Successfully indexed {len(ids)} documents in ChromaDB collection '{collection_name}'")
        except Exception as e:
            logger.error(f"Failed to index documents in ChromaDB: {e}")

    def query_documents(self, collection_name: str, query_text: str, n_results: int = 4) -> list[dict]:
        """Queries ChromaDB collection for semantically relevant documents."""
        if not CHROMADB_AVAILABLE or not self.chroma_client:
            logger.warning("ChromaDB is unavailable. Returning empty search results.")
            return []

        try:
            collection = self.chroma_client.get_collection(name=collection_name)
            query_vector = self._get_embedding(query_text)

            results = collection.query(
                query_embeddings=[query_vector],
                n_results=n_results
            )

            formatted = []
            if results and "documents" in results and len(results["documents"]) > 0:
                docs = results["documents"][0]
                metas = results["metadatas"][0] if "metadatas" in results else [{}] * len(docs)
                ids = results["ids"][0] if "ids" in results else [""] * len(docs)
                
                for doc_id, doc_text, doc_meta in zip(ids, docs, metas):
                    formatted.append({
                        "id": doc_id,
                        "text": doc_text,
                        "metadata": doc_meta
                    })
            return formatted
        except Exception as e:
            logger.error(f"Failed to query ChromaDB collection '{collection_name}': {e}")
            return []

    def _get_embedding(self, text: str) -> list[float]:
        """Retrieves embeddings from local Ollama or falls back to SimpleTextEmbedder."""
        if self.ollama_client:
            try:
                # nomic-embed-text is standard, check if loaded
                resp = self.ollama_client.embeddings(model="nomic-embed-text", prompt=text)
                return resp["embedding"]
            except Exception:
                pass
        return self.fallback_embedder.embed_text(text)

    # ═══════════════════════════════════════════════
    # MULTI-MODEL LLM RESPONSE RESOLUTION
    # ═══════════════════════════════════════════════

    async def generate_response(self, prompt: str, system_instruction: str = None) -> str:
        """
        Generates text completion using the multi-model priority list:
        Gemini 1.5 Flash -> OpenAI GPT-4o -> Local Ollama (llama3.1:8b).
        """
        # 0. Try global APIKeyManager if available
        if self.key_manager:
            try:
                # RAG Generation is a "thinking" task
                client, model, key_str = self.key_manager.get_client("thinking")
                logger.info(f"[RAGAdvisor] Querying LLM via APIKeyManager (model: {model})...")
                messages = []
                if system_instruction:
                    messages.append({"role": "system", "content": system_instruction})
                messages.append({"role": "user", "content": prompt})

                resp = await client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.2,
                    max_tokens=500
                )
                return resp.choices[0].message.content.strip()
            except Exception as e:
                err_msg = str(e).lower()
                is_rate_limit = "429" in err_msg or "quota" in err_msg or "rate limit" in err_msg
                if is_rate_limit:
                    self.key_manager.mark_exhausted(key_str)
                logger.warning(f"[RAGAdvisor] APIKeyManager query failed: {e}. Falling back to default RAG models...")

        # 1. Try Gemini
        if self.gemini_client:
            try:
                logger.info("[RAGAdvisor] Querying Gemini 1.5 Flash...")
                full_prompt = f"{system_instruction}\n\n{prompt}" if system_instruction else prompt
                resp = self.gemini_client.generate_content(full_prompt)
                if resp.text:
                    return resp.text.strip()
            except Exception as e:
                logger.warning(f"Gemini generation failed: {e}. Falling back to OpenAI...")

        # 2. Try OpenAI
        if self.openai_client:
            try:
                logger.info("[RAGAdvisor] Querying OpenAI GPT-4o...")
                messages = []
                if system_instruction:
                    messages.append({"role": "system", "content": system_instruction})
                messages.append({"role": "user", "content": prompt})

                resp = self.openai_client.chat.completions.create(
                    model="gpt-4o",
                    messages=messages,
                    max_tokens=300
                )
                return resp.choices[0].message.content.strip()
            except Exception as e:
                logger.warning(f"OpenAI generation failed: {e}. Falling back to local Ollama...")

        # 3. Try Ollama (Local/Offline)
        if self.ollama_client:
            try:
                logger.info("[RAGAdvisor] Querying Local Ollama (llama3.1)...")
                messages = []
                if system_instruction:
                    messages.append({"role": "system", "content": system_instruction})
                messages.append({"role": "user", "content": prompt})

                resp = self.ollama_client.chat(
                    model="llama3.1:8b",
                    messages=messages
                )
                return resp["message"]["content"].strip()
            except Exception as e:
                logger.error(f"Local Ollama generation failed: {e}")

        return "AI Advisor Fallback: System was unable to contact Gemini, OpenAI, or Ollama. Please verify your keys and connection."
