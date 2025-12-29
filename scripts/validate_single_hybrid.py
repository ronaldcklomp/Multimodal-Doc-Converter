#!/usr/bin/env python3
"""
VALIDATION: Single-file extraction with PNG count verification.
Process ONLY Hybrid_electric_vehicles_and_their_challenges.pdf
Verify PNG count > 5 before proceeding to remaining files.
"""

import gc
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.mmrag_converter.v2.processor import V2DocumentProcessor

print("=" * 80)
print("VALIDATION: Single File Extraction - Hybrid PDF")
print("=" * 80)

# Setup
test_folder = Path("./test")
raw_extracts_dir = Path("./data/raw_extracts")
raw_assets_dir = Path("./data/assets/raw")

# Clean slate
print("\n[CLEAN SLATE]")
for d in [raw_extracts_dir, raw_assets_dir]:
    if d.exists():
        shutil.rmtree(d)
        print(f"✓ Deleted: {d}")

for d in [raw_extracts_dir, raw_assets_dir]:
    d.mkdir(parents=True, exist_ok=True)
    print(f"✓ Created: {d}")

# Find ONLY the Hybrid file
pdf_file = test_folder / "Hybrid_electric_vehicles_and_their_challenges.pdf"

if not pdf_file.exists():
    print(f"\n✗ ERROR: {pdf_file} not found!")
    sys.exit(1)

size_mb = pdf_file.stat().st_size / (1024 * 1024)
print(f"\n[PROCESSING HYBRID FILE]")
print(f"File: {pdf_file.name} ({size_mb:.1f} MB)")

# Process with V2DocumentProcessor
processor = V2DocumentProcessor(
    output_dir=str(raw_assets_dir.parent),
    enable_ocr=False,
)

print("\n⏳ Extracting...")
try:
    chunks = []
    for chunk in processor.process_document(str(pdf_file)):
        chunks.append(chunk.model_dump(mode="json"))
    
    chunk_count = len(chunks)
    print(f"✓ Extracted {chunk_count} chunks")
    
    # Save to JSONL
    if chunks:
        doc_id = chunks[0]["doc_id"]
        jsonl_path = raw_extracts_dir / f"{doc_id}_{pdf_file.stem}.jsonl"
        
        with open(jsonl_path, 'w', encoding='utf-8') as f:
            for chunk in chunks:
                f.write(json.dumps(chunk, ensure_ascii=False) + '\n')
        
        print(f"✓ Saved to: {jsonl_path.name}")
    
    # Memory cleanup
    del chunks
    gc.collect()
    print("✓ Memory cleared")
    
except Exception as e:
    print(f"✗ FAILED: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# CRITICAL: Verify PNG count
print("\n[VERIFICATION]")
png_list = os.listdir(raw_assets_dir)
png_count = len([f for f in png_list if f.endswith('.png')])

print(f"PNG files in {raw_assets_dir}:")
print(f"  Count: {png_count}")

if png_count > 0:
    print(f"\n✓ First 10 assets:")
    for i, png in enumerate(sorted([f for f in png_list if f.endswith('.png')])[:10], 1):
        png_path = raw_assets_dir / png
        size_kb = png_path.stat().st_size / 1024
        print(f"  {i}. {png} ({size_kb:.1f}KB)")
else:
    print(f"\n✗ NO PNG FILES FOUND!")
    print("✗ Asset extraction failed - do NOT proceed to remaining files")
    sys.exit(1)

# Verify JSONL
jsonl_files = [f for f in os.listdir(raw_extracts_dir) if f.endswith('.jsonl')]
print(f"\nJSONL files: {len(jsonl_files)}")
for jf in jsonl_files:
    lines = sum(1 for _ in open(raw_extracts_dir / jf))
    print(f"  - {jf}: {lines} chunks")

# Final verdict
print("\n" + "=" * 80)
if png_count > 5:
    print("✅ VALIDATION SUCCESSFUL")
    print(f"✅ PNG count ({png_count}) exceeds threshold (5)")
    print("✅ Ready to process remaining files (PCWorld, Combat Aircraft)")
else:
    print("❌ VALIDATION FAILED")
    print(f"❌ PNG count ({png_count}) below threshold (5)")
    print("❌ Asset extraction is broken - DO NOT proceed")
    sys.exit(1)

print("=" * 80)
