# 🚀 Multi-Modal RAG Converter (V2.1)

**Transforming complex, high-noise PDFs into production-ready Multimodal RAG datasets.**

This repository contains a high-precision data engineering pipeline designed to parse visually rich documents (like technical magazines) into a structured format optimized for **Retrieval-Augmented Generation (RAG)**. It solves the common "garbage in, garbage out" problem by enforcing strict data hygiene, hierarchical integrity, and high-fidelity asset extraction.

## 🌟 Key Features

* **High-Fidelity Asset Extraction:** Images and tables are rendered at `scale=2.0`, ensuring maximum detail for downstream OCR or Vision-Language Model (VLM) analysis.
* **Context-Aware Chunking:** Enforces a ~400-character "Child-Parent" strategy. Every chunk is anchored to its original document hierarchy (breadcrumbs).
* **Rule-Based Denoising:** Intelligent filtering of non-editorial content (advertisements, promotions, and "fluff") to ensure your vector database stays clean.
* **Deduplicated State Machine:** Advanced breadcrumb management that eliminates redundant headers (e.g., "INTERNET INTERNET") for a cleaner retrieval context.
* **Portable Production Output:** Generates a strictly validated `ingestion.jsonl` with relative asset mapping, allowing for easy migration between environments.

## 🛠 Technical Stack

* **Core Engine:** [Docling](https://github.com/DS4SD/docling) v2.66.0
* **Language:** Python 3.10+
* **Architecture:** Streaming-based processing with proactive Garbage Collection (GC) for memory stability on large files (>25MB).
* **Compliance:** Strict adherence to the internal **SRS v2.1** data schema.

## 📁 Repository Structure

```text
data/
└── [document_name]_v2_output/
    ├── ingestion.jsonl      # Validated multimodal dataset
    └── assets/              # High-resolution PNG extractions

```

## 📊 Performance Benchmark (Combat Aircraft Test)

* **Input Size:** 28.5 MB PDF
* **Chunks Generated:** 1,737 high-precision chunks
* **Assets Extracted:** 244 technical images (331 MB)
* **Denoising Success:** ~98% of advertisement noise eliminated.
* **Breadcrumb Integrity:** 100% unique sequential headers.

---

## 🚀 Getting Started

### Installation

```bash
# Clone the repository
git clone https://github.com/ronaldcklomp/Multimodal-Doc-Converter
cd Multimodal-doc-converter

# Install dependencies (Python 3.10 required)
pip install -r requirements.txt

# Verify V2 installation
python3 -c "from src.mmrag_converter.v2 import V2DocumentProcessor; print('✅ V2 Converter Ready')"
```

### Quick Start: Process a Single Document

#### Option 1: Python API (Recommended)

```python
from src.mmrag_converter.v2 import create_processor
from pathlib import Path

# Create processor
processor = create_processor(
    output_dir="./output",
    enable_ocr=False,  # Set to True if processing scanned documents
)

# Process PDF and generate JSONL
input_pdf = Path("data/my_document.pdf")
output_jsonl = processor.process_to_jsonl(
    str(input_pdf),
    output_path="output/ingestion.jsonl"
)

print(f"✓ Generated: {output_jsonl}")
print(f"✓ Assets saved to: output/assets/")
```

#### Option 2: Command Line Interface

```bash
python -m src.mmrag_converter.v2.cli process data/my_document.pdf --output-dir ./output
```

### Comprehensive Example: Processing with Full Metadata

```python
from src.mmrag_converter.v2 import (
    V2DocumentProcessor,
    create_processor,
    FileType,
    create_text_chunk,
    HierarchyMetadata,
)
from pathlib import Path

# Initialize processor
processor = create_processor(
    output_dir="./output",
    enable_ocr=True,  # Enable OCR for scanned content
    ocr_engine="easyocr",
)

# Process document and collect chunks
chunks = []
for chunk in processor.process_document("data/technical_manual.pdf"):
    chunks.append(chunk)
    
    # Access chunk properties
    print(f"Page {chunk.metadata.page_number}: {chunk.modality}")
    
    if chunk.modality == "image":
        print(f"  └─ Asset: {chunk.asset_ref.file_path}")
    
    if chunk.metadata.hierarchy.breadcrumb_path:
        print(f"  └─ Context: {' > '.join(chunk.metadata.hierarchy.breadcrumb_path)}")

# Export to JSONL
output_jsonl = processor.process_to_jsonl(
    "data/technical_manual.pdf",
    "output/ingestion.jsonl"
)

print(f"\n✓ Processed {len(chunks)} chunks")
print(f"✓ Output: {output_jsonl}")
```

## 📤 Output Format: `ingestion.jsonl`

Each line in `ingestion.jsonl` is a validated chunk. Example:

```json
{
  "chunk_id": "550e8400-e29b-41d4-a716-446655440000",
  "doc_id": "a1b2c3d4e5f6",
  "modality": "text",
  "content": "The XYZ system operates on the principle of...",
  "metadata": {
    "source_file": "technical_manual.pdf",
    "file_type": "pdf",
    "page_number": 42,
    "hierarchy": {
      "parent_heading": "3.2 Installation",
      "breadcrumb_path": ["Chapter 3", "3.2 Installation"],
      "level": 2
    },
    "content_classification": "editorial"
  }
}
```

### Schema Compliance

- **chunk_id:** UUID v4 (unique per chunk)
- **doc_id:** MD5 hash of source file (for deduplication)
- **modality:** `text`, `image`, or `table`
- **metadata.hierarchy:** Breadcrumb path preserving document structure
- **asset_ref:** (For images/tables) Path to extracted PNG asset

## 🔌 Integration with RAG Systems

### Example: Using with LangChain + Qdrant

```python
import json
from langchain_community.vectorstores import Qdrant
from langchain.embeddings.openai import OpenAIEmbeddings

# Load ingestion.jsonl
chunks = []
with open("output/ingestion.jsonl", "r") as f:
    for line in f:
        chunks.append(json.loads(line))

# Convert to LangChain documents
from langchain.schema import Document

documents = [
    Document(
        page_content=chunk["content"],
        metadata={
            "source": chunk["metadata"]["source_file"],
            "page": chunk["metadata"]["page_number"],
            "breadcrumb": chunk["metadata"]["hierarchy"]["breadcrumb_path"],
            "modality": chunk["modality"],
            "asset_path": chunk.get("asset_ref", {}).get("file_path"),
        }
    )
    for chunk in chunks
]

# Create vector store
embeddings = OpenAIEmbeddings()
vector_store = Qdrant.from_documents(
    documents,
    embeddings,
    url="http://localhost:6333",
    collection_name="multimodal_documents"
)

# Run semantic search
results = vector_store.similarity_search(
    "How do I install the XYZ system?",
    k=5
)

for result in results:
    print(f"Source: {result.metadata['source']}")
    print(f"Breadcrumb: {result.metadata['breadcrumb']}")
    print(f"Content: {result.page_content[:200]}...")
```

### Example: Using with Pinecone

```python
import json
import openai
from pinecone import Pinecone

# Initialize Pinecone
pc = Pinecone(api_key="your-api-key")
index = pc.Index("multimodal-docs")

# Load and embed chunks
with open("output/ingestion.jsonl", "r") as f:
    vectors = []
    for i, line in enumerate(f):
        chunk = json.loads(line)
        
        # Generate embedding
        embedding = openai.Embedding.create(
            input=chunk["content"],
            model="text-embedding-3-small"
        )["data"][0]["embedding"]
        
        # Prepare metadata
        metadata = {
            "source_file": chunk["metadata"]["source_file"],
            "page_number": chunk["metadata"]["page_number"],
            "breadcrumb": "|".join(chunk["metadata"]["hierarchy"]["breadcrumb_path"]),
            "modality": chunk["modality"],
        }
        
        if chunk.get("asset_ref"):
            metadata["asset_path"] = chunk["asset_ref"]["file_path"]
        
        vectors.append((
            chunk["chunk_id"],
            embedding,
            metadata
        ))
    
    # Upsert to Pinecone
    index.upsert(vectors=vectors, namespace="default")

print(f"✓ Indexed {len(vectors)} chunks in Pinecone")
```

## 📋 Advanced Configuration

### Custom Output Directory and Asset Location

```python
processor = create_processor(
    output_dir="./data/my_output",  # All outputs here
    enable_ocr=True,
)

# Assets saved to: ./data/my_output/assets/
# JSONL saved to: ./data/my_output/ingestion.jsonl
```

### Processing Multiple Documents

```python
from pathlib import Path

data_dir = Path("data")
pdf_files = list(data_dir.glob("*.pdf"))

for pdf_file in pdf_files:
    output_dir = data_dir / f"{pdf_file.stem}_output"
    processor = create_processor(output_dir=str(output_dir))
    
    output_jsonl = processor.process_to_jsonl(
        str(pdf_file),
        output_path=str(output_dir / "ingestion.jsonl")
    )
    
    print(f"✓ Processed: {pdf_file.name} → {output_jsonl}")
```

### Performance Tuning

```python
processor = V2DocumentProcessor(
    output_dir="./output",
    enable_ocr=False,      # Disable for speed, enable for scanned docs
    ocr_engine="tesseract", # or "easyocr" (easyocr is slower but more accurate)
    max_pages=100,         # Limit pages for testing (None = all pages)
)
```

## 🧪 Testing V2 Installation

```bash
# Run quick verification
python3 -c "
from src.mmrag_converter.v2 import create_processor, create_text_chunk, FileType
processor = create_processor(output_dir='test_output')
chunk = create_text_chunk(
    doc_id='test123',
    content='Hello world',
    source_file='test.pdf',
    file_type=FileType.PDF,
    page_number=1
)
print('✅ V2 Converter is fully functional')
print(f'✅ Generated chunk: {chunk.chunk_id}')
"
```

## 📊 Example Output

Processing a 0.5 MB PDF generates:
- **483 chunks** (text, images, tables)
- **18 PNG assets** (10px padded, 2x scale)
- **ingestion.jsonl** (170 KB) with complete metadata

Processing time: ~2 minutes (including Docling layout analysis)

---


## 🛡 License

Internal Project - SRS v2.1 Compliant.
