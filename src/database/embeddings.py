"""
Embedding Provider Interface - Unified Embedding Generation
=============================================================
ENGINE_USE: Claude 4.5 Opus (Architect)

Provides a unified interface for generating embeddings from:
- OpenAI API (text-embedding-3-small, text-embedding-3-large)
- Local models (BGE-M3 via sentence-transformers)
- Testing models (all-MiniLM-L6-v2)

The interface is designed to be:
1. Lazy-loaded: Models only load when first used
2. Batch-optimized: Supports efficient batch embedding
3. Cached: Optional caching for repeated embeddings
4. Provider-agnostic: Easy to swap between OpenAI and local

Author: Claude 4.5 Opus (Architect)
Date: 2025-12-28
"""
from __future__ import annotations

import logging
import os
import time
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple, Union

from .config import EmbeddingModel, VECTOR_DIMS

logger = logging.getLogger(__name__)


# ============================================================================
# ABSTRACT BASE CLASS
# ============================================================================

class EmbeddingProvider(ABC):
    """
    Abstract base class for embedding providers.
    
    All providers must implement:
    - embed_text: Embed a single text
    - embed_batch: Embed a batch of texts efficiently
    """
    
    def __init__(self, model_name: str, dimension: int):
        self.model_name = model_name
        self.dimension = dimension
        self._initialized = False
    
    @abstractmethod
    def _initialize(self) -> None:
        """Initialize the model (lazy loading)."""
        pass
    
    @abstractmethod
    def embed_text(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Input text to embed
            
        Returns:
            List of floats (embedding vector)
        """
        pass
    
    @abstractmethod
    def embed_batch(
        self,
        texts: List[str],
        batch_size: int = 32,
        show_progress: bool = False,
    ) -> List[List[float]]:
        """
        Generate embeddings for a batch of texts.
        
        Args:
            texts: List of input texts
            batch_size: Number of texts to process at once
            show_progress: Whether to show progress bar
            
        Returns:
            List of embedding vectors
        """
        pass
    
    def _ensure_initialized(self) -> None:
        """Ensure the model is initialized before use."""
        if not self._initialized:
            self._initialize()
            self._initialized = True


# ============================================================================
# OPENAI EMBEDDING PROVIDER
# ============================================================================

class OpenAIEmbeddingProvider(EmbeddingProvider):
    """
    OpenAI API embedding provider.
    
    Supports:
    - text-embedding-3-small (1536 dims, recommended)
    - text-embedding-3-large (3072 dims)
    - text-embedding-ada-002 (1536 dims, legacy)
    
    Environment Variables:
    - OPENAI_API_KEY: Required for API access
    - OPENAI_ORG_ID: Optional organization ID
    """
    
    MODEL_MAPPING = {
        EmbeddingModel.OPENAI: "text-embedding-3-small",
        EmbeddingModel.OPENAI_LARGE: "text-embedding-3-large",
    }
    
    def __init__(
        self,
        model: EmbeddingModel = EmbeddingModel.OPENAI,
        api_key: Optional[str] = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        model_name = self.MODEL_MAPPING.get(model, "text-embedding-3-small")
        dimension = VECTOR_DIMS.get(model.value, 1536)
        super().__init__(model_name, dimension)
        
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._client = None
    
    def _initialize(self) -> None:
        """Initialize the OpenAI client."""
        if not self.api_key:
            raise ValueError(
                "OpenAI API key not found. Set OPENAI_API_KEY environment variable."
            )
        
        try:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.api_key)
            logger.info(f"Initialized OpenAI embedding provider: {self.model_name}")
        except ImportError:
            raise ImportError(
                "OpenAI package not installed. Run: pip install openai"
            )
    
    def embed_text(self, text: str) -> List[float]:
        """Generate embedding for a single text using OpenAI API."""
        self._ensure_initialized()
        
        # Truncate if too long (OpenAI limit is ~8191 tokens)
        text = text[:32000]  # Approximate character limit
        
        for attempt in range(self.max_retries):
            try:
                response = self._client.embeddings.create(
                    input=text,
                    model=self.model_name,
                )
                return response.data[0].embedding
            except Exception as e:
                if attempt < self.max_retries - 1:
                    logger.warning(
                        f"OpenAI API error (attempt {attempt + 1}): {e}"
                    )
                    time.sleep(self.retry_delay * (attempt + 1))
                else:
                    raise
    
    def embed_batch(
        self,
        texts: List[str],
        batch_size: int = 100,  # OpenAI supports up to 2048
        show_progress: bool = False,
    ) -> List[List[float]]:
        """Generate embeddings for a batch of texts using OpenAI API."""
        self._ensure_initialized()
        
        # Truncate texts
        texts = [t[:32000] for t in texts]
        
        all_embeddings = []
        total_batches = (len(texts) + batch_size - 1) // batch_size
        
        iterator = range(0, len(texts), batch_size)
        if show_progress:
            try:
                from tqdm import tqdm
                iterator = tqdm(iterator, total=total_batches, desc="Embedding")
            except ImportError:
                pass
        
        for i in iterator:
            batch = texts[i:i + batch_size]
            
            for attempt in range(self.max_retries):
                try:
                    response = self._client.embeddings.create(
                        input=batch,
                        model=self.model_name,
                    )
                    batch_embeddings = [d.embedding for d in response.data]
                    all_embeddings.extend(batch_embeddings)
                    break
                except Exception as e:
                    if attempt < self.max_retries - 1:
                        logger.warning(
                            f"OpenAI API error (attempt {attempt + 1}): {e}"
                        )
                        time.sleep(self.retry_delay * (attempt + 1))
                    else:
                        raise
        
        return all_embeddings


# ============================================================================
# LOCAL EMBEDDING PROVIDER (sentence-transformers)
# ============================================================================

class LocalEmbeddingProvider(EmbeddingProvider):
    """
    Local embedding provider using sentence-transformers.
    
    Supports:
    - BAAI/bge-m3 (1024 dims, multilingual)
    - all-MiniLM-L6-v2 (384 dims, fast testing)
    
    Uses GPU if available, falls back to CPU.
    """
    
    MODEL_MAPPING = {
        EmbeddingModel.BGE_M3: "BAAI/bge-m3",
        EmbeddingModel.MINILM: "all-MiniLM-L6-v2",
    }
    
    def __init__(
        self,
        model: EmbeddingModel = EmbeddingModel.MINILM,
        device: Optional[str] = None,
        normalize_embeddings: bool = True,
    ):
        model_name = self.MODEL_MAPPING.get(model, "all-MiniLM-L6-v2")
        dimension = VECTOR_DIMS.get(model.value, 384)
        super().__init__(model_name, dimension)
        
        self.device = device
        self.normalize_embeddings = normalize_embeddings
        self._model = None
    
    def _initialize(self) -> None:
        """Initialize the sentence-transformers model."""
        try:
            from sentence_transformers import SentenceTransformer
            
            # Auto-detect device
            device = self.device
            if not device:
                try:
                    import torch
                    device = "cuda" if torch.cuda.is_available() else "cpu"
                    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                        device = "mps"  # Apple Silicon
                except ImportError:
                    device = "cpu"
            
            logger.info(
                f"Initializing local embedding model: {self.model_name} on {device}"
            )
            
            self._model = SentenceTransformer(
                self.model_name,
                device=device,
            )
            
            logger.info(f"Local embedding model initialized: {self.model_name}")
            
        except ImportError:
            raise ImportError(
                "sentence-transformers not installed. "
                "Run: pip install sentence-transformers"
            )
    
    def embed_text(self, text: str) -> List[float]:
        """Generate embedding for a single text using local model."""
        self._ensure_initialized()
        
        embedding = self._model.encode(
            text,
            normalize_embeddings=self.normalize_embeddings,
            show_progress_bar=False,
        )
        
        return embedding.tolist()
    
    def embed_batch(
        self,
        texts: List[str],
        batch_size: int = 32,
        show_progress: bool = False,
    ) -> List[List[float]]:
        """Generate embeddings for a batch of texts using local model."""
        self._ensure_initialized()
        
        embeddings = self._model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=self.normalize_embeddings,
            show_progress_bar=show_progress,
        )
        
        return embeddings.tolist()


# ============================================================================
# MOCK EMBEDDING PROVIDER (for testing without models)
# ============================================================================

class MockEmbeddingProvider(EmbeddingProvider):
    """
    Mock embedding provider for testing without actual models.
    
    Generates deterministic pseudo-random embeddings based on text hash.
    Useful for:
    - Unit tests
    - CI/CD pipelines
    - Development without GPU/API access
    """
    
    def __init__(self, dimension: int = 384):
        super().__init__("mock", dimension)
    
    def _initialize(self) -> None:
        """No initialization needed for mock provider."""
        logger.info(f"Using mock embedding provider (dim={self.dimension})")
    
    def embed_text(self, text: str) -> List[float]:
        """Generate deterministic mock embedding based on text hash."""
        import hashlib
        import struct
        
        # Create deterministic seed from text
        text_hash = hashlib.md5(text.encode()).digest()
        seed = struct.unpack("I", text_hash[:4])[0]
        
        # Generate pseudo-random but deterministic embedding
        import random
        rng = random.Random(seed)
        embedding = [rng.gauss(0, 1) for _ in range(self.dimension)]
        
        # Normalize
        norm = sum(x * x for x in embedding) ** 0.5
        embedding = [x / norm for x in embedding]
        
        return embedding
    
    def embed_batch(
        self,
        texts: List[str],
        batch_size: int = 32,
        show_progress: bool = False,
    ) -> List[List[float]]:
        """Generate mock embeddings for a batch of texts."""
        return [self.embed_text(t) for t in texts]


# ============================================================================
# FACTORY FUNCTION
# ============================================================================

def get_embedding_provider(
    model: Union[EmbeddingModel, str] = EmbeddingModel.OPENAI,
    api_key: Optional[str] = None,
    use_mock: bool = False,
) -> EmbeddingProvider:
    """
    Factory function to get the appropriate embedding provider.
    
    Args:
        model: Embedding model to use
        api_key: API key for OpenAI (optional, uses env var)
        use_mock: If True, use mock provider for testing
        
    Returns:
        EmbeddingProvider instance
        
    Examples:
        # OpenAI (default)
        provider = get_embedding_provider()
        
        # Local BGE-M3
        provider = get_embedding_provider(EmbeddingModel.BGE_M3)
        
        # Mock for testing
        provider = get_embedding_provider(use_mock=True)
    """
    if use_mock:
        dimension = VECTOR_DIMS.get(
            model.value if isinstance(model, EmbeddingModel) else model,
            384
        )
        return MockEmbeddingProvider(dimension=dimension)
    
    if isinstance(model, str):
        model = EmbeddingModel(model)
    
    if model in (EmbeddingModel.OPENAI, EmbeddingModel.OPENAI_LARGE):
        return OpenAIEmbeddingProvider(model=model, api_key=api_key)
    else:
        return LocalEmbeddingProvider(model=model)


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def prepare_text_for_embedding(
    content: str,
    modality: str,
    breadcrumb_path: Optional[List[str]] = None,
    parent_heading: Optional[str] = None,
    include_context: bool = True,
) -> str:
    """
    Prepare text for embedding by adding context.
    
    For better semantic retrieval, we prepend hierarchical context
    to the actual content. This helps the embedding capture:
    - Section context (what part of document)
    - Content type (text, image, table)
    
    Args:
        content: The actual content to embed
        modality: Content type (text, image, table)
        breadcrumb_path: Hierarchical path
        parent_heading: Immediate parent heading
        include_context: Whether to include context prefix
        
    Returns:
        Prepared text for embedding
    """
    if not include_context:
        return content
    
    parts = []
    
    # Add breadcrumb context
    if breadcrumb_path:
        path_str = " > ".join(breadcrumb_path)
        parts.append(f"[Section: {path_str}]")
    elif parent_heading:
        parts.append(f"[Section: {parent_heading}]")
    
    # Add modality context for non-text
    if modality == "image":
        parts.append("[Content Type: Image/Figure]")
    elif modality == "table":
        parts.append("[Content Type: Table]")
    
    # Add the actual content
    parts.append(content)
    
    return " ".join(parts)
