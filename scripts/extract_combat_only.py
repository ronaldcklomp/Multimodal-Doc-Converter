#!/usr/bin/env python3
"""Extract Combat Aircraft only with full error handling."""

import gc
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.mmrag_converter.v2.processor import V2DocumentProcessor

test_folder = Path("./test")
raw_extracts_dir = Path("./data/raw_extracts")
raw_assets_dir = Path("./data/assets/raw")

pdf_file = test_folder / "Combat Aircraft - August 2025 UK.pdf"

print(f"{'='*80}")
print(f"COMBAT AIRCRAFT EXTRACTION")
print(f"{'='*80}\n")

if not pdf_file.exists():
    print(f"✗ ERROR: {pdf_file} not found!")
    sys.exit(1)

size_mb = pdf_file.stat().st_size / (1024*1024)
print(f"File: {pdf_file.name} ({size_mb:.1f} MB)")

processor = V2DocumentProcessor(
    output_dir=str(raw_assets_dir.parent),
    enable_ocr=False,
)

print(f"⏳ Processing... (may take 30+ minutes)\n")

try:
    chunks = []
    for i, chunk in enumerate(processor.process_document(str(pdf_file))):
        chunks.append(chunk.model_dump(mode="json"))
        if (i + 1) % 100 == 0:
            print(f"  ✓ {i+1} chunks extracted...")
    
    chunk_count = len(chunks)
    print(f"\n✓ COMPLETE: Extracted {chunk_count} chunks")
    
    if chunks:
        doc_id = chunks[0]["doc_id"]
        jsonl_path = raw_extracts_dir / f"{doc_id}_Combat_Aircraft_-_August_2025_UK.jsonl"
        
        with open(jsonl_path, 'w', encoding='utf-8') as f:
            for chunk in chunks:
                f.write(json.dumps(chunk, ensure_ascii=False) + '\n')
        
        print(f"✓ Saved to: {jsonl_path.name}")
    
    del chunks
    gc.collect()
    
    print(f"\n{'='*80}")
    print(f"✅ COMBAT AIRCRAFT DONE: {chunk_count} chunks")
    print(f"{'='*80}")
    
except Exception as e:
    print(f"\n✗ FATAL ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
