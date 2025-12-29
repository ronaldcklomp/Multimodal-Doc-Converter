#!/usr/bin/env python3
"""
FINAL COMPLIANCE AUDIT - All Processed Documents
=================================================
Audits all V2 processed documents in data/ directory

Author: Claude
Date: 2025-12-28
"""
import json
import sys
from pathlib import Path
from collections import Counter


def audit_directory(base_dir: Path):
    """Audit all processed documents."""
    
    print("=" * 80)
    print("FINAL V2 PRODUCTION COMPLIANCE AUDIT")
    print("=" * 80)
    
    # Find all ingestion.jsonl files
    jsonl_files = list(base_dir.glob("*/ingestion.jsonl"))
    
    if not jsonl_files:
        print("❌ No ingestion.jsonl files found in data/")
        return False
    
    total_files = len(jsonl_files)
    total_chunks = 0
    total_assets = 0
    all_asset_paths = []
    modality_counts = Counter()
    
    print(f"\nTotal Files Processed: {total_files}")
    print("=" * 80)
    
    for jsonl_file in sorted(jsonl_files):
        doc_name = jsonl_file.parent.name
        
        # Load chunks
        chunks = []
        with open(jsonl_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    chunks.append(json.loads(line))
        
        # Count assets
        asset_count = sum(1 for c in chunks if c.get("asset_ref"))
        
        # Count modalities
        for chunk in chunks:
            modality_counts[chunk.get("modality", "unknown")] += 1
        
        # Collect asset paths
        for chunk in chunks:
            if chunk.get("asset_ref") and chunk["asset_ref"].get("file_path"):
                all_asset_paths.append(
                    (doc_name, chunk["asset_ref"]["file_path"])
                )
        
        total_chunks += len(chunks)
        total_assets += asset_count
        
        print(f"\n📄 {doc_name}:")
        print(f"   Chunks: {len(chunks)}")
        print(f"   Assets: {asset_count}")
    
    print("\n" + "=" * 80)
    print("AGGREGATE STATISTICS")
    print("=" * 80)
    print(f"Total Files Processed: {total_files}")
    print(f"Total Chunks: {total_chunks}")
    print(f"Total Assets (PNG): {total_assets}")
    print(f"\nModality Breakdown:")
    for modality, count in modality_counts.most_common():
        print(f"  {modality}: {count}")
    
    # Verify asset existence
    print("\n" + "=" * 80)
    print("ASSET INTEGRITY CHECK")
    print("=" * 80)
    
    missing_assets = []
    checked_assets = set()
    
    for doc_name, asset_path in all_asset_paths:
        # Extract filename from path
        asset_file = Path(asset_path).name
        
        # Check in both locations
        locations = [
            Path(f"data/{doc_name}/assets/{asset_file}"),
            Path(f"data/assets/raw/{asset_file}")
        ]
        
        found = False
        for loc in locations:
            if loc.exists() and str(loc) not in checked_assets:
                found = True
                checked_assets.add(str(loc))
                break
        
        if not found:
            missing_assets.append(asset_path)
    
    if missing_assets:
        print(f"❌ FAIL: {len(missing_assets)} assets missing on disk")
        for path in missing_assets[:5]:
            print(f"   - {path}")
        if len(missing_assets) > 5:
            print(f"   ... and {len(missing_assets) - 5} more")
    else:
        print(f"✅ PASS: All {total_assets} referenced assets exist on disk")
    
    # Check data/assets/raw/
    raw_assets = Path("data/assets/raw")
    if raw_assets.exists():
        png_files = list(raw_assets.glob("*.png"))
        print(f"\nPNG files in data/assets/raw/: {len(png_files)}")
    
    print("\n" + "=" * 80)
    print("VERDICT")
    print("=" * 80)
    
    if missing_assets:
        print("⚠️  WARNING: Some assets missing")
        return False
    else:
        print("✅ FULL COMPLIANCE: All requirements met")
        return True


def main():
    """Main execution."""
    base_dir = Path("data")
    
    if not base_dir.exists():
        print(f"❌ Directory not found: {base_dir}")
        sys.exit(1)
    
    success = audit_directory(base_dir)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
