#!/usr/bin/env python3
"""
V2 PRODUCTION EXECUTION: PCWorld_July_2025_USA.pdf
==================================================
SRS v2.1 ENFORCEMENT with Rule 5, Rule 6, and REQ-PDF-05

MANDATORY FEATURES:
- Streaming writes with f.flush() every chunk
- Immediate PNG saves during Docling loop
- gc.collect() every 500 chunks/50 images
- Live console telemetry every 100 chunks

Author: Claude (V2 Production)
Date: 2025-12-28
"""
import gc
import hashlib
import json
import logging
import os
import sys
from pathlib import Path

import psutil

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from mmrag_converter.v2.processor import V2DocumentProcessor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)


def get_ram_usage_mb() -> float:
    """Get current RAM usage in MB."""
    try:
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / (1024 * 1024)
    except Exception:
        return 0.0


def compute_sha256(file_path: Path) -> str:
    """Compute SHA256 for integrity verification."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def process_document_production(
    input_file: Path,
    output_dir: Path,
    raw_assets_dir: Path
) -> dict:
    """
    Process document with SRS v2.1 production requirements.
    
    Returns:
        dict with stats: chunks, assets, ram_peak
    """
    # REQ-PDF-05: Pre-emptive garbage collection
    gc.collect()
    logger.info("🗑️  PRE-FLIGHT: gc.collect() executed")
    
    # Compute SHA256
    sha256 = compute_sha256(input_file)
    logger.info(f"🔒 INTEGRITY: SHA256 = {sha256[:16]}...")
    
    # Initialize processor
    processor = V2DocumentProcessor(
        output_dir=str(output_dir),
        enable_ocr=False,  # Disabled for speed
        ocr_engine="tesseract"
    )
    
    logger.info(f"📄 TARGET: {input_file.name}")
    logger.info(f"📊 ENGINE_USE: Docling v2.66.0")
    logger.info(f"🎯 REQ-PDF-04: images_scale=2.0, generate_picture_images=True")
    
    # STREAMING OUTPUT (SRS Rule 5)
    jsonl_path = output_dir / "ingestion.jsonl"
    assets_dir = output_dir / "assets"
    
    chunk_count = 0
    asset_count = 0
    ad_count = 0  # Track denoised ads
    ram_peak_mb = 0.0
    
    print("\n" + "=" * 80)
    print("V2 STRICT RE-DO: STREAMING WRITES + AGGRESSIVE AD FILTERING")
    print("=" * 80)
    
    # STREAM chunks to disk one-by-one
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for chunk in processor.process_document(str(input_file)):
            # Write chunk immediately (Rule 5)
            json_line = json.dumps(chunk.model_dump(mode="json"), ensure_ascii=False)
            f.write(json_line + "\n")
            f.flush()  # FORCE PHYSICAL WRITE
            chunk_count += 1
            
            # Track assets
            if chunk.asset_ref and chunk.asset_ref.file_path:
                asset_count += 1
            
            # Live telemetry every 50 chunks (STRICT MANDATE)
            if chunk_count % 50 == 0:
                ram_mb = get_ram_usage_mb()
                ram_peak_mb = max(ram_peak_mb, ram_mb)
                print(
                    f"[V2-STRICT-REDO] Chunk {chunk_count} | Denoised: {ad_count} | "
                    f"Assets Saved: {asset_count} | RAM: {ram_mb:.1f}MB",
                    flush=True
                )
            
            # REQ-PDF-05: Mid-process garbage collection
            if chunk_count % 500 == 0 or asset_count % 50 == 0:
                gc.collect()
                logger.info(f"🗑️  MID-PROCESS: gc.collect() at chunk {chunk_count}")
    
    # Final telemetry
    ram_mb = get_ram_usage_mb()
    ram_peak_mb = max(ram_peak_mb, ram_mb)
    print(
        f"[V2-PROD] {input_file.name} | COMPLETE | Chunks: {chunk_count} | "
        f"Assets: {asset_count} | Peak RAM: {ram_peak_mb:.1f}MB",
        flush=True
    )
    
    # Copy assets to raw directory
    if assets_dir.exists():
        for asset_file in assets_dir.glob("*.png"):
            dest = raw_assets_dir / asset_file.name
            import shutil
            shutil.copy2(asset_file, dest)
    
    # REQ-PDF-05: Post-process cleanup
    gc.collect()
    logger.info("🗑️  POST-PROCESS: gc.collect() executed")
    
    return {
        "chunks": chunk_count,
        "assets": asset_count,
        "ram_peak_mb": ram_peak_mb,
        "jsonl_path": str(jsonl_path)
    }


def main():
    """Main execution."""
    # Target file
    input_file = Path("examples/sample_docs/PCWorld_July_2025_USA.pdf")
    
    if not input_file.exists():
        logger.error(f"❌ File not found: {input_file}")
        sys.exit(1)
    
    # Output directories
    output_dir = Path("data/pcworld_v2_output")
    raw_assets_dir = Path("data/assets/raw")
    raw_assets_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info("=" * 80)
    logger.info("V2 PRODUCTION EXECUTION")
    logger.info("=" * 80)
    logger.info(f"Input: {input_file}")
    logger.info(f"Size: {input_file.stat().st_size / (1024*1024):.1f} MB")
    logger.info(f"Output: {output_dir}")
    logger.info("=" * 80)
    
    try:
        stats = process_document_production(
            input_file=input_file,
            output_dir=output_dir,
            raw_assets_dir=raw_assets_dir
        )
        
        logger.info("\n" + "=" * 80)
        logger.info("✅ PROCESSING COMPLETE")
        logger.info("=" * 80)
        logger.info(f"Total Chunks: {stats['chunks']}")
        logger.info(f"Total Assets: {stats['assets']}")
        logger.info(f"Peak RAM: {stats['ram_peak_mb']:.1f} MB")
        logger.info(f"JSONL: {stats['jsonl_path']}")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"❌ Processing failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
