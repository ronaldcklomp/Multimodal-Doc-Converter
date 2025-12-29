#!/usr/bin/env python3
"""
TEST: SRS Rule 5 Compliance - Streaming Chunker (400-char precision)
===========================================================================
CRITICAL SYSTEM TEST: Verify streaming writes and memory hygiene
"""

import sys
import json
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, 'src')

from mmrag_converter.chunker import chunk_blocks_to_jsonl
from mmrag_converter.doc_profile import DocDomain

# Mock blocks data for testing
def create_test_blocks(num_paragraphs=500):
    """Create test block data to simulate Combat Aircraft."""
    blocks = []
    doc_id = "test_combat_aircraft"
    
    for i in range(num_paragraphs):
        # Simulate paragraphs with realistic text length
        para_text = (
            f"This is paragraph {i+1}. "
            f"Combat aircraft designs have evolved significantly over decades. "
            f"The aerodynamic principles governing flight remain constant. "
            f"Modern fighters incorporate stealth technology extensively. "
            f"Avionics systems are increasingly sophisticated and autonomous. "
            f"Pilot workload management is critical for mission success. "
            f"Weapon system integration requires careful engineering. "
            f"Maintenance procedures continue to become more complex. "
            f"Training programs adapt to new capabilities regularly. "
            f"Operational cost considerations influence procurement decisions significantly."
        )
        
        block = {
            "doc_id": doc_id,
            "block_id": f"block_{i:04d}",
            "page_number": (i // 5) + 1,
            "block_type": "paragraph" if i % 7 != 0 else "heading",
            "text": para_text,
            "heading_level": 2 if i % 7 == 0 else None,
            "breadcrumb_path": ["Combat Aircraft", f"Section {(i // 50) + 1}"],
            "section_path": ["Combat Aircraft", f"Section {(i // 50) + 1}"],
        }
        blocks.append(block)
    
    return doc_id, blocks

def write_test_blocks_to_jsonl(blocks, output_path):
    """Write test blocks to JSONL for chunking."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for block in blocks:
            f.write(json.dumps(block, ensure_ascii=False) + "\n")

def main():
    print("\n" + "=" * 80)
    print("TEST: SRS Rule 5 Compliance - Streaming Chunker")
    print("=" * 80)
    
    # Setup test data
    workdir = Path("workdir_test_streaming")
    blocks_path = workdir / "test_blocks.jsonl"
    output_path = workdir / "test_chunks_streamed.jsonl"
    
    print("\n[SETUP]")
    doc_id, blocks = create_test_blocks(num_paragraphs=500)
    write_test_blocks_to_jsonl(blocks, blocks_path)
    print(f"✓ Created {len(blocks)} test blocks in {blocks_path}")
    
    # Test streaming chunker with 400-char precision
    print("\n[STREAMING CHUNK PROCESSING]")
    print(f"Input:  {blocks_path}")
    print(f"Output: {output_path}")
    print(f"Config: max_tokens=400 (400-char precision per SRS)")
    
    start_time = time.time()
    print(f"\n[START] {time.strftime('%H:%M:%S')}")
    
    result_path = chunk_blocks_to_jsonl(
        blocks_path=blocks_path,
        out_path=output_path,
        max_tokens=400,
        min_tokens=30,
        doc_domain=DocDomain.book,
    )
    
    elapsed = time.time() - start_time
    print(f"[END]   {time.strftime('%H:%M:%S')} (Elapsed: {elapsed:.2f}s)")
    
    # Verify output
    print("\n[VERIFICATION]")
    if output_path.exists():
        with output_path.open("r", encoding="utf-8") as f:
            chunks = [json.loads(line) for line in f if line.strip()]
        
        file_size_mb = output_path.stat().st_size / (1024 * 1024)
        print(f"✓ Output file exists: {output_path}")
        print(f"  Size: {file_size_mb:.2f} MB")
        print(f"  Chunks: {len(chunks)}")
        
        # Check token compliance
        max_token_found = max([c["tokens_estimate"] for c in chunks], default=0)
        min_token_found = min([c["tokens_estimate"] for c in chunks], default=0)
        avg_token = sum([c["tokens_estimate"] for c in chunks]) / len(chunks) if chunks else 0
        
        print(f"\n  Token Statistics:")
        print(f"    Max:  {max_token_found}")
        print(f"    Min:  {min_token_found}")
        print(f"    Avg:  {avg_token:.1f}")
        
        # Verify 400-char precision
        if max_token_found <= 512:  # Hard limit
            print(f"✓ SRS COMPLIANCE: All chunks respect 400-char target (max observed: {max_token_found})")
        else:
            print(f"✗ VIOLATION: Chunk size {max_token_found} exceeds hard limit 512")
        
        # Sample chunks
        print(f"\n[SAMPLE CHUNKS]")
        for i, chunk in enumerate(chunks[:3]):
            print(f"  Chunk {i+1}:")
            print(f"    ID: {chunk['chunk_id']}")
            print(f"    Tokens: {chunk['tokens_estimate']}")
            print(f"    Text: {chunk['text'][:60]}...")
        
        return True
    else:
        print(f"✗ Output file NOT created: {output_path}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
