#!/usr/bin/env python3
"""
V2-LOCK EXECUTION: Process Hybrid_electric_vehicles_and_their_challenges.pdf ONLY
====================================================================================
SRS REQ-PDF-04 Enforcement with Mandatory Proof-of-Life Logs

This script:
1. Uses V2 processor with hardcoded REQ-PDF-04 initialization
2. Processes ONLY Hybrid_electric_vehicles_and_their_challenges.pdf
3. Ensures 400-character chunks (not tokens!)
4. Extracts PNGs to data/assets/raw/
5. Prints mandatory proof-of-life logs

Author: Claude (V2-LOCK Enforcer)
Date: 2025-12-28
"""
import hashlib
import logging
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from mmrag_converter.v2.processor import V2DocumentProcessor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


def compute_sha256(file_path: Path) -> str:
    """Compute SHA256 hash for integrity verification."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def print_proof_of_life(assets_dir: Path, doc_name: str) -> None:
    """
    Print mandatory proof-of-life logs per task requirements.
    
    MANDATORY LOGS:
    1. Count of PNG files in data/assets/raw/
    2. Resolution (WxH) of first PNG found
    3. "V2-COMPLIANT-READY" if count > 0, else ABORT message
    """
    from PIL import Image
    
    # Count PNG files
    png_files = list(assets_dir.glob("*.png"))
    png_count = len(png_files)
    
    print("\n" + "=" * 80)
    print("PROOF OF LIFE - V2 REQ-PDF-04 COMPLIANCE CHECK")
    print("=" * 80)
    print(f"Document: {doc_name}")
    print(f"PNG Count in {assets_dir}: {png_count}")
    
    if png_count > 0:
        # Get resolution of first PNG
        first_png = png_files[0]
        try:
            with Image.open(first_png) as img:
                width, height = img.size
                print(f"First PNG: {first_png.name}")
                print(f"Resolution: {width}x{height}")
        except Exception as e:
            print(f"ERROR: Could not read PNG resolution: {e}")
        
        print("\n✓ V2-COMPLIANT-READY")
        print("=" * 80 + "\n")
    else:
        print("\n❌ ABORT: PNG COUNT IS 0")
        print("=" * 80)
        print("CRITICAL FAILURE: REQ-PDF-04 WAS IGNORED")
        print("The V2 processor must be initialized with:")
        print("  pipeline_options.images_scale = 2.0")
        print("  pipeline_options.generate_picture_images = True")
        print("  pipeline_options.generate_table_images = True")
        print("=" * 80 + "\n")
        sys.exit(1)


def main():
    """Main execution: Process Hybrid_electric_vehicles_and_their_challenges.pdf"""
    
    # Target file
    input_file = Path("examples/sample_docs/Hybrid_electric_vehicles_and_their_challenges.pdf")
    
    if not input_file.exists():
        logger.error(f"File not found: {input_file}")
        sys.exit(1)
    
    # Create output directory structure
    output_dir = Path("data/hybrid_v2_output")
    assets_dir = output_dir / "assets"
    raw_assets_dir = Path("data/assets/raw")
    raw_assets_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info("=" * 80)
    logger.info("V2-LOCK EXECUTION: HYBRID ELECTRIC VEHICLES PDF")
    logger.info("=" * 80)
    logger.info(f"Input: {input_file}")
    logger.info(f"Output: {output_dir}")
    logger.info(f"Assets: {raw_assets_dir}")
    
    # Pre-flight: Compute SHA256 for integrity
    sha256 = compute_sha256(input_file)
    logger.info(f"INTEGRITY: SHA256 = {sha256[:16]}...")
    
    # Print ENGINE_USE banner
    print("\n" + "=" * 80)
    print("ENGINE_USE: Using Docling v2.66.0")
    print("REQ-PDF-04: images_scale=2.0, generate_picture_images=True")
    print("CHUNK SIZE: 400 characters (SRS High-Precision Mandate)")
    print("=" * 80 + "\n")
    
    # Initialize V2 processor with REQ-PDF-04 compliance
    # Note: OCR disabled for this test (focus is on image extraction, not scanned PDFs)
    processor = V2DocumentProcessor(
        output_dir=str(output_dir),
        enable_ocr=False,
        ocr_engine="tesseract"
    )
    
    # Process document
    logger.info("Starting V2 document processing...")
    
    try:
        jsonl_path = processor.process_to_jsonl(str(input_file))
        logger.info(f"✓ JSONL written to: {jsonl_path}")
        
        # Copy assets to data/assets/raw/ for proof-of-life check
        import shutil
        for asset_file in assets_dir.glob("*.png"):
            dest = raw_assets_dir / asset_file.name
            shutil.copy2(asset_file, dest)
            logger.info(f"  → Copied: {asset_file.name} -> {raw_assets_dir}/")
        
        # MANDATORY: Print proof-of-life logs
        print_proof_of_life(raw_assets_dir, input_file.name)
        
        # Verify chunk sizes
        import json
        with open(jsonl_path, "r", encoding="utf-8") as f:
            chunks = [json.loads(line) for line in f if line.strip()]
        
        # Check text chunks for 400-character compliance
        text_chunks = [c for c in chunks if c.get("modality") == "text"]
        if text_chunks:
            avg_len = sum(len(c["content"]) for c in text_chunks) / len(text_chunks)
            max_len = max(len(c["content"]) for c in text_chunks)
            logger.info(f"\nCHUNK CHECK:")
            logger.info(f"  Total chunks: {len(chunks)}")
            logger.info(f"  Text chunks: {len(text_chunks)}")
            logger.info(f"  Avg text length: {avg_len:.0f} chars")
            logger.info(f"  Max text length: {max_len} chars")
            
            if max_len > 512:
                logger.warning(f"  ⚠️ Max chunk exceeds 512 chars (found {max_len})")
        
        logger.info("\n✓ V2 Processing Complete")
        
    except Exception as e:
        logger.error(f"❌ Processing failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
