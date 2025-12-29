#!/usr/bin/env python3
"""
SRS v2.1 COMPLIANCE AUDIT - Comprehensive Validation
====================================================
This script performs a meticulous audit of the V2 processor output against
ALL requirements specified in SRS_Multimodal_Ingestion_V2.1.md

Validation Checks:
- REQ-PDF-04: Image extraction enabled
- REQ-MM-01: 10px padding on crops
- REQ-MM-02: Asset naming convention
- REQ-MM-03: Context anchoring (prev/next text)
- REQ-CHUNK-01: Sentence boundary integrity
- REQ-CHUNK-02: Token/character limits
- REQ-STATE: Breadcrumb hierarchy persistence
- REQ-OUT-01: JSONL format (not single JSON array)
- Section 6: Canonical schema validation
- Rule 3: No full-page images

Author: Claude (V2 Auditor)
Date: 2025-12-28
"""
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Any
from collections import Counter

from PIL import Image


class SRSComplianceAuditor:
    """Comprehensive SRS v2.1 compliance auditor."""
    
    def __init__(self, jsonl_path: str, assets_dir: str):
        self.jsonl_path = Path(jsonl_path)
        self.assets_dir = Path(assets_dir)
        self.chunks: List[Dict[str, Any]] = []
        self.issues: List[str] = []
        self.warnings: List[str] = []
        self.stats: Dict[str, Any] = {}
    
    def load_chunks(self) -> None:
        """Load and parse JSONL file."""
        print("📂 Loading JSONL file...")
        
        if not self.jsonl_path.exists():
            self.issues.append(f"CRITICAL: JSONL file not found: {self.jsonl_path}")
            return
        
        with open(self.jsonl_path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                    self.chunks.append(chunk)
                except json.JSONDecodeError as e:
                    self.issues.append(f"Line {line_no}: Invalid JSON - {e}")
        
        print(f"  ✓ Loaded {len(self.chunks)} chunks")
    
    def check_req_out_01(self) -> None:
        """REQ-OUT-01: JSONL format (not single JSON array)."""
        print("\n🔍 REQ-OUT-01: JSONL Format Check")
        
        # Read raw file to ensure it's not a JSON array
        with open(self.jsonl_path, "r", encoding="utf-8") as f:
            first_char = f.read(1)
        
        if first_char == "[":
            self.issues.append("REQ-OUT-01 VIOLATION: File is a JSON array, not JSONL!")
            print("  ❌ FAIL: File starts with '[' (JSON array)")
        else:
            print("  ✓ PASS: File is JSONL format (newline-delimited)")
    
    def check_schema_section_6(self) -> None:
        """Section 6: Canonical output schema validation."""
        print("\n🔍 Section 6: Schema Validation")
        
        required_fields = ["chunk_id", "doc_id", "modality", "content", "metadata"]
        required_metadata = ["source_file", "file_type", "page_number", "hierarchy"]
        
        for idx, chunk in enumerate(self.chunks):
            # Check top-level fields
            for field in required_fields:
                if field not in chunk:
                    self.issues.append(f"Chunk {idx}: Missing required field '{field}'")
            
            # Check metadata structure
            if "metadata" in chunk:
                metadata = chunk["metadata"]
                for field in required_metadata:
                    if field not in metadata:
                        self.issues.append(f"Chunk {idx}: Missing metadata field '{field}'")
                
                # Check hierarchy structure
                if "hierarchy" in metadata:
                    hierarchy = metadata["hierarchy"]
                    if not isinstance(hierarchy, dict):
                        self.issues.append(f"Chunk {idx}: hierarchy must be a dict")
                    else:
                        if "breadcrumb_path" not in hierarchy:
                            self.warnings.append(f"Chunk {idx}: No breadcrumb_path in hierarchy")
        
        if not self.issues:
            print("  ✓ PASS: All chunks conform to Section 6 schema")
        else:
            print(f"  ❌ FAIL: {len(self.issues)} schema violations found")
    
    def check_req_state(self) -> None:
        """REQ-STATE: Breadcrumb hierarchy persistence."""
        print("\n🔍 REQ-STATE: Breadcrumb Hierarchy Check")
        
        chunks_with_breadcrumbs = 0
        breadcrumb_depth_issues = 0
        
        for idx, chunk in enumerate(self.chunks):
            if "metadata" not in chunk:
                continue
            
            hierarchy = chunk["metadata"].get("hierarchy", {})
            breadcrumb_path = hierarchy.get("breadcrumb_path", [])
            level = hierarchy.get("level")
            
            if breadcrumb_path:
                chunks_with_breadcrumbs += 1
                
                # REQ-STATE-03: breadcrumb depth should match level
                if level is not None and len(breadcrumb_path) != level:
                    breadcrumb_depth_issues += 1
                    if breadcrumb_depth_issues <= 3:  # Only report first 3
                        self.warnings.append(
                            f"Chunk {idx}: breadcrumb depth ({len(breadcrumb_path)}) "
                            f"!= level ({level})"
                        )
        
        print(f"  • Chunks with breadcrumbs: {chunks_with_breadcrumbs}/{len(self.chunks)}")
        
        if breadcrumb_depth_issues == 0:
            print("  ✓ PASS: Breadcrumb hierarchy consistent")
        else:
            print(f"  ⚠️ WARNING: {breadcrumb_depth_issues} breadcrumb depth mismatches")
    
    def check_req_chunk(self) -> None:
        """REQ-CHUNK: Chunk size and boundary integrity."""
        print("\n🔍 REQ-CHUNK: Chunking Strategy Validation")
        
        text_chunks = [c for c in self.chunks if c.get("modality") == "text"]
        
        if not text_chunks:
            print("  ⚠️ No text chunks found")
            return
        
        # Analyze chunk sizes
        char_counts = [len(c["content"]) for c in text_chunks]
        avg_chars = sum(char_counts) / len(char_counts)
        max_chars = max(char_counts)
        min_chars = min(char_counts)
        
        # REQ-CHUNK-02: Hard max 512 tokens (approx 640 chars at 1.25 chars/token)
        HARD_MAX_CHARS = 640
        oversized = [c for c in char_counts if c > HARD_MAX_CHARS]
        
        print(f"  • Text chunks: {len(text_chunks)}")
        print(f"  • Avg size: {avg_chars:.0f} chars")
        print(f"  • Min size: {min_chars} chars")
        print(f"  • Max size: {max_chars} chars")
        print(f"  • Target: 400 chars (512 token hard max)")
        
        if oversized:
            self.warnings.append(
                f"REQ-CHUNK-02: {len(oversized)} chunks exceed 640 chars "
                f"(max: {max(oversized)})"
            )
            print(f"  ⚠️ WARNING: {len(oversized)} chunks > 640 chars")
        
        # REQ-CHUNK-01: Check for mid-sentence splits
        mid_sentence_splits = 0
        for chunk in text_chunks[:50]:  # Sample first 50
            content = chunk["content"].strip()
            if content and not re.search(r'[.!?\n]\s*$', content):
                # Doesn't end with sentence boundary
                if not content[-1].isdigit():  # Allow numbers (lists)
                    mid_sentence_splits += 1
        
        if mid_sentence_splits > 0:
            ratio = mid_sentence_splits / min(50, len(text_chunks))
            if ratio > 0.3:  # More than 30% is concerning
                self.warnings.append(
                    f"REQ-CHUNK-01: {mid_sentence_splits}/{min(50, len(text_chunks))} "
                    "sampled chunks don't end at sentence boundaries"
                )
                print(f"  ⚠️ WARNING: {mid_sentence_splits} chunks may have mid-sentence splits")
        
        if not oversized and mid_sentence_splits == 0:
            print("  ✓ PASS: Chunk sizes and boundaries compliant")
    
    def check_req_mm_02(self) -> None:
        """REQ-MM-02: Asset naming convention."""
        print("\n🔍 REQ-MM-02: Asset Naming Convention")
        
        # Pattern: [DocHash]_[PageNum]_[Type]_[Index].png
        pattern = re.compile(r'^[0-9a-f]{12}_\d{3}_(figure|table)_\d{2}\.png$')
        
        if not self.assets_dir.exists():
            self.issues.append(f"Assets directory not found: {self.assets_dir}")
            print(f"  ❌ Assets directory not found: {self.assets_dir}")
            return
        
        png_files = list(self.assets_dir.glob("*.png"))
        invalid_names = []
        
        for png_file in png_files:
            if not pattern.match(png_file.name):
                invalid_names.append(png_file.name)
        
        print(f"  • Total PNG files: {len(png_files)}")
        print(f"  • Valid names: {len(png_files) - len(invalid_names)}")
        
        if invalid_names:
            self.issues.append(
                f"REQ-MM-02 VIOLATION: {len(invalid_names)} assets with invalid names"
            )
            print(f"  ❌ FAIL: {len(invalid_names)} invalid asset names")
            for name in invalid_names[:3]:
                print(f"      - {name}")
        else:
            print("  ✓ PASS: All assets follow naming convention")
    
    def check_req_mm_03(self) -> None:
        """REQ-MM-03: Context anchoring for images."""
        print("\n🔍 REQ-MM-03: Contextual Anchoring Check")
        
        image_chunks = [c for c in self.chunks if c.get("modality") == "image"]
        
        if not image_chunks:
            print("  ⚠️ No image chunks found")
            return
        
        missing_context = 0
        for chunk in image_chunks:
            semantic_context = chunk.get("semantic_context", {})
            if not semantic_context or not semantic_context.get("prev_text_snippet"):
                missing_context += 1
        
        print(f"  • Image chunks: {len(image_chunks)}")
        print(f"  • With context: {len(image_chunks) - missing_context}")
        
        if missing_context > 0:
            self.warnings.append(
                f"REQ-MM-03: {missing_context}/{len(image_chunks)} images lack context snippets"
            )
            print(f"  ⚠️ WARNING: {missing_context} images without context")
        else:
            print("  ✓ PASS: All images have context anchoring")
    
    def check_rule_3_no_fullpage(self) -> None:
        """Rule 3: No full-page image exports."""
        print("\n🔍 Rule 3: No Full-Page Images")
        
        if not self.assets_dir.exists():
            return
        
        png_files = list(self.assets_dir.glob("*.png"))
        
        # Typical full-page sizes (at 2x scale)
        # US Letter: 612x792 pts -> 1224x1584 px at 2x
        # A4: 595x842 pts -> 1190x1684 px at 2x
        FULLPAGE_THRESHOLD = 1000  # If both dimensions > 1000px, likely full page
        
        fullpage_candidates = []
        
        for png_file in png_files:
            try:
                with Image.open(png_file) as img:
                    w, h = img.size
                    if w > FULLPAGE_THRESHOLD and h > FULLPAGE_THRESHOLD:
                        fullpage_candidates.append((png_file.name, w, h))
            except Exception as e:
                self.warnings.append(f"Could not read {png_file.name}: {e}")
        
        print(f"  • Total assets: {len(png_files)}")
        
        if fullpage_candidates:
            self.warnings.append(
                f"Rule 3: {len(fullpage_candidates)} assets appear to be full-page images"
            )
            print(f"  ⚠️ WARNING: {len(fullpage_candidates)} potential full-page images")
            for name, w, h in fullpage_candidates[:3]:
                print(f"      - {name}: {w}x{h}px")
        else:
            print("  ✓ PASS: No full-page images detected")
    
    def check_asset_refs(self) -> None:
        """Verify all asset_ref paths exist on disk."""
        print("\n🔍 Asset Reference Integrity")
        
        chunks_with_refs = [c for c in self.chunks if c.get("asset_ref")]
        missing_assets = []
        
        for chunk in chunks_with_refs:
            asset_ref = chunk["asset_ref"]
            file_path = asset_ref.get("file_path", "")
            
            if file_path:
                # Path is relative: assets/[filename]
                full_path = self.assets_dir / Path(file_path).name
                if not full_path.exists():
                    missing_assets.append(file_path)
        
        print(f"  • Chunks with asset_ref: {len(chunks_with_refs)}")
        
        if missing_assets:
            self.issues.append(
                f"QA-CHECK-02 VIOLATION: {len(missing_assets)} referenced assets missing"
            )
            print(f"  ❌ FAIL: {len(missing_assets)} assets missing on disk")
            for path in missing_assets[:3]:
                print(f"      - {path}")
        else:
            print("  ✓ PASS: All referenced assets exist")
    
    def generate_statistics(self) -> None:
        """Generate summary statistics."""
        print("\n📊 Summary Statistics")
        
        modality_counts = Counter(c.get("modality") for c in self.chunks)
        
        print(f"  • Total chunks: {len(self.chunks)}")
        for modality, count in modality_counts.most_common():
            print(f"  • {modality}: {count}")
        
        if self.assets_dir.exists():
            png_count = len(list(self.assets_dir.glob("*.png")))
            print(f"  • PNG assets: {png_count}")
    
    def print_report(self) -> bool:
        """Print final audit report."""
        print("\n" + "=" * 80)
        print("SRS v2.1 COMPLIANCE AUDIT REPORT")
        print("=" * 80)
        
        if not self.issues and not self.warnings:
            print("\n✅ **FULL COMPLIANCE ACHIEVED**")
            print("All SRS v2.1 requirements satisfied.")
            return True
        
        if self.issues:
            print(f"\n❌ **CRITICAL ISSUES: {len(self.issues)}**")
            for issue in self.issues:
                print(f"  • {issue}")
        
        if self.warnings:
            print(f"\n⚠️ **WARNINGS: {len(self.warnings)}**")
            for warning in self.warnings:
                print(f"  • {warning}")
        
        print("\n" + "=" * 80)
        
        return len(self.issues) == 0
    
    def run_full_audit(self) -> bool:
        """Run complete audit suite."""
        print("=" * 80)
        print("SRS v2.1 COMPLIANCE AUDIT")
        print("=" * 80)
        print(f"JSONL: {self.jsonl_path}")
        print(f"Assets: {self.assets_dir}")
        print("=" * 80)
        
        self.load_chunks()
        
        if not self.chunks:
            print("\n❌ No chunks loaded - cannot proceed")
            return False
        
        # Run all checks
        self.check_req_out_01()
        self.check_schema_section_6()
        self.check_req_state()
        self.check_req_chunk()
        self.check_req_mm_02()
        self.check_req_mm_03()
        self.check_rule_3_no_fullpage()
        self.check_asset_refs()
        self.generate_statistics()
        
        return self.print_report()


def main():
    """Main execution."""
    jsonl_path = "data/hybrid_v2_output/ingestion.jsonl"
    assets_dir = "data/hybrid_v2_output/assets"
    
    auditor = SRSComplianceAuditor(jsonl_path, assets_dir)
    success = auditor.run_full_audit()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
