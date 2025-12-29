# PDF Requirements Compliance Analysis & Fix Plan
## Based on "Multimodal Document Converter — Requirements Specification 1.3.1.md"

**Analysis Date**: 2025-12-27  
**Scope**: PDF documents only (digital, scanned, mixed)  
**Requirements Version**: 1.3.1  
**Current Implementation Version**: Based on codebase analysis

---

## Executive Summary

The current implementation provides a functional PDF conversion pipeline but does not fully comply with the v1.3.1 requirements specification. Key gaps include optional Surya integration (should be mandatory), incomplete OCR preprocessing, missing schema fields, and lack of comprehensive error handling. The implementation follows an older requirements document (v0.1.x) rather than the stricter v1.3.1 specification.

---

## 1. Critical Compliance Gaps

### 1.1 Engine Integration (HIGH PRIORITY)

| Requirement | Status | Issue |
|-------------|--------|-------|
| **REQ-TEXT-2**: Surya mandatory for PDF layout | ❌ Non-compliant | Surya is optional with fallback to heuristics. v1.3.1 requires Surya as mandatory with RuntimeError on failure. |
| **REQ-FORMAT-5**: Surya confidence scores | ❌ Non-compliant | Missing `heading_confidence` and block confidence scores in `blocks_structured.jsonl`. |
| **ENGINE PINNING IS MANDATORY** | ❌ Non-compliant | No hardcoded engine version enforcement. Should fail on wrong version detection. |

### 1.2 OCR Pipeline (HIGH PRIORITY)

| Requirement | Status | Issue |
|-------------|--------|-------|
| **REQ-OCR-5**: Mandatory preprocessing | ❌ Non-compliant | Placeholder functions for deskew/binarize/denoise. Missing actual implementation. |
| **REQ-OCR-6**: Language handling | ⚠️ Partial | Auto-detection exists but missing Surya language classifier integration. |
| **REQ-OCR-7**: OHRBench metrics | ❌ Non-compliant | Missing `ocr_quality_metrics` with character/word accuracy and structural preservation. |

### 1.3 Schema Compliance (HIGH PRIORITY)

| Schema | Missing Fields | Requirement Reference |
|--------|----------------|----------------------|
| `doc_meta.json` | `format_type`, `format_metadata`, `validation` with `input_sha256` and `schema_version` | §4.1 |
| `blocks_structured.jsonl` | `physical_context` (required when `is_rootless:true`), `heading_confidence`, `format_specific` | §4.4 |
| `chunks_text.jsonl` | `source_blocks`, `tokenizer_spec`, `overflow_chunk_id`, `source_format`, `format_specific` | §4.5 |
| `chunks_multimodal.jsonl` | `asset_integrity` with SHA256 hashes, `modality_completeness_score` | §4.6 |
| **Missing entirely**: `ingestion.jsonl` | Complete unified schema missing | §4.8 (Primary output) |

### 1.4 Error Handling (MEDIUM PRIORITY)

| Requirement | Status | Issue |
|-------------|--------|-------|
| **REQ-CLI-3**: Exit codes 64-77 | ❌ Non-compliant | Missing detailed error code framework (Appendix B). |
| **ERR_ENGINE_UNAVAILABLE** (76) | ❌ Non-compliant | No explicit engine install requirement messages. |
| **ERR_SCHEMA_INVALID** (75) | ❌ Non-compliant | No schema validation failures. |

### 1.5 Resource Constraints (MEDIUM PRIORITY)

| Requirement | Status | Issue |
|-------------|--------|-------|
| **NFR-4**: Resource Safety | ❌ Non-compliant | No per-format memory caps (PDF: 768MB, etc.) or CPU throttling. |
| **Resource throttling at OS level** | ❌ Non-compliant | No Linux cgroups/Windows Job Objects implementation. |

### 1.6 Quality Evaluation (MEDIUM PRIORITY)

| Requirement | Status | Issue |
|-------------|--------|-------|
| **REQ-QA-4**: OHRBench metrics | ❌ Non-compliant | Missing `ocr_quality_metrics` and `multimodal_metrics`. |
| **REQ-QA-5**: Unified schema validation | ❌ Non-compliant | No `ingestion.jsonl` schema validation. |
| **Format-specific metrics** | ❌ Non-compliant | Missing PDF-specific metrics like `min_surya_confidence`, `max_layout_errors`. |

### 1.7 State Persistence (LOW PRIORITY)

| Requirement | Status | Issue |
|-------------|--------|-------|
| **REQ-STATE-4**: State persistence file | ❌ Non-compliant | Missing `workdir/state/<doc_id>.state.json` with format-specific metadata. |

### 1.8 Figure-Caption Association (MEDIUM PRIORITY)

| Requirement | Status | Issue |
|-------------|--------|-------|
| **REQ-MM-6**: Figure-caption association | ❌ Non-compliant | Missing mandatory figure-caption pairing via spatial proximity heuristic. |
| **REQ-FIG-2**: Caption linking | ❌ Non-compliant | Missing caption text in figure metadata. |

---

## 2. Partial Compliance Areas

### 2.1 CLI Commands
- ✅ **REQ-CLI-1/2**: All required commands exist (`inspect`, `render-pages`, `extract-text`, etc.)
- ⚠️ **REQ-CLI-3**: Missing detailed error codes but basic error handling exists.

### 2.2 Text Extraction
- ✅ **REQ-TEXT-1/1b**: `pages_raw.jsonl` and `doc_meta.json` created
- ✅ **REQ-TEXT-4**: `is_scanned_like` field present
- ⚠️ **REQ-TEXT-2**: Layout-aware extraction exists but Surya is optional

### 2.3 OCR Fallback
- ✅ **REQ-OCR-1**: `pages_with_ocr.jsonl` created
- ✅ **REQ-OCR-2**: OCR only applied to `is_scanned_like=true` pages
- ✅ **REQ-OCR-3**: `is_blank_page` field present
- ⚠️ **REQ-OCR-4**: Language parameter supports 'auto' but missing Surya classifier

### 2.4 Structure Analysis
- ✅ **REQ-STRUCT-1/2/3**: `blocks_structured.jsonl` and `structure_report.txt` created
- ✅ **REQ-STATE-1/2/3**: `ContextState` implemented with breadcrumb inheritance

### 2.5 Chunking
- ✅ **REQ-CHUNK-1**: `chunks_text.jsonl` created
- ✅ **REQ-CHUNK-2**: Sentence boundary splitting implemented
- ✅ **REQ-CHUNK-3**: Required fields present
- ✅ **REQ-CHUNK-4**: Deduplication works
- ⚠️ **REQ-CHUNK-5**: Contextual overlap partially implemented but missing static overlap logic
- ⚠️ **REQ-CHUNK-6**: Hard max chunk size (512 tokens) not properly enforced
- ⚠️ **REQ-CHUNK-7**: Semantic overlap with embeddings implemented but optional

### 2.6 Multimodal Export
- ✅ **REQ-MM-1/2/3**: `chunks_multimodal.jsonl` created with image linking
- ❌ Missing asset integrity checks and modality completeness score

---

## 3. Implementation vs Requirements Matrix

| Requirement Category | v1.3.1 Requirement | Current Implementation | Compliance |
|---------------------|-------------------|------------------------|------------|
| **Engine Integration** | Surya mandatory | Surya optional | ❌ |
| **OCR Preprocessing** | Deskew+binary+denoise | Placeholder functions | ❌ |
| **Schema Fields** | Complete schemas | Missing 30+ fields | ❌ |
| **Error Codes** | 64-77 detailed codes | Basic error handling | ❌ |
| **Resource Limits** | Memory/CPU caps | No limits | ❌ |
| **Quality Metrics** | OHRBench metrics | Basic metrics only | ❌ |
| **Unified Schema** | `ingestion.jsonl` primary | Not implemented | ❌ |
| **State Persistence** | `state/*.state.json` | Not implemented | ❌ |
| **Figure-Caption** | Mandatory pairing | Not implemented | ❌ |

---

## 4. Root Cause Analysis

1. **Requirements Drift**: Current code follows v0.1.x requirements while being evaluated against v1.3.1.
2. **Incremental Development**: Features implemented incrementally without full v1.3.1 compliance.
3. **Optional Dependencies**: Surya treated as optional enhancement rather than mandatory component.
4. **Schema Evolution**: Output schemas haven't been updated to match v1.3.1 specifications.
5. **Testing Gap**: Lack of comprehensive test suite for v1.3.1 requirements.

---

## 5. Fix Plan: Step-by-Step Approach

### Phase 1: Critical Compliance (Week 1-2)
**Goal**: Achieve mandatory requirements for PDF processing.

#### Step 1.1: Make Surya Mandatory
- Modify `layout_analysis.py` to remove fallback and raise `RuntimeError` if Surya fails
- Update `extract_layout_aware_text()` to log Surya version and require successful analysis
- Add Surya confidence scores to `blocks_structured.jsonl`

#### Step 1.2: Implement OCR Preprocessing
- Replace placeholder functions in `ocr_engine.py` with actual implementations:
  - `_deskew_image()` using OpenCV/scikit-image
  - `_binarize_adaptive_gaussian()` with block_size=15
  - `_denoise_gaussian()` with sigma=1.2
- Add preprocessing parameter logging to `quality_report.json`

#### Step 1.3: Add Missing Schema Fields
- Update `doc_profile.py` to include `format_type`, `format_metadata`, `validation`
- Modify `structure_analyzer.py` to add `physical_context` for rootless blocks
- Update `chunker.py` to include missing fields in chunk schemas
- Add `asset_integrity` with SHA256 to `multimodal_export.py`

### Phase 2: Error Handling & Resource Management (Week 3)
**Goal**: Implement robust error handling and resource constraints.

#### Step 2.1: Error Code Framework
- Define error codes 64-77 in `errors.py` module
- Update CLI to return appropriate exit codes
- Add error messages matching Appendix B specifications

#### Step 2.2: Resource Constraints
- Implement memory monitoring in `pdf_loader.py` and `text_extractor.py`
- Add CPU throttling (Linux cgroups/Windows Job Objects)
- Implement per-format caps: PDF (768MB, 90s/page)

#### Step 2.3: Engine Version Pinning
- Hardcode Surya version requirement (v0.17.0)
- Add version check at module import
- Fail with `ERR_ENGINE_UNAVAILABLE` (76) if wrong version

### Phase 3: Quality Metrics & Unified Schema (Week 4)
**Goal**: Implement comprehensive quality evaluation and unified output schema.

#### Step 3.1: OHRBench Metrics
- Extend `quality_metrics.py` to include:
  - `ocr_quality_metrics` (character_accuracy, word_accuracy, structural_preservation)
  - `multimodal_metrics` (figure_caption_pairing_ratio, table_structure_preservation)
- Add PDF-specific metrics: `min_surya_confidence`, `max_layout_errors`

#### Step 3.2: Implement `ingestion.jsonl`
- Create new module `unified_schema.py` with `IngestionChunk` dataclass
- Modify `convert` command to output `ingestion.jsonl` as primary artifact
- Maintain backward compatibility with legacy schemas

#### Step 3.3: Figure-Caption Association
- Implement spatial proximity heuristic in `figure_extractor.py`
- Add caption detection and pairing logic
- Include `unpaired_figures_ratio` in quality metrics

### Phase 4: State Persistence & Advanced Features (Week 5)
**Goal**: Complete all remaining requirements.

#### Step 4.1: State Persistence
- Modify `state_machine.py` to save/load `state/*.state.json`
- Include format-specific metadata in state file
- Ensure state survives pipeline interruptions

#### Step 4.2: Enhanced Chunking
- Fix hard max token limits (512 for text, 1024 for atomic units)
- Implement proper static contextual overlap (REQ-CHUNK-5)
- Validate semantic overlap implementation

#### Step 4.3: Cryptographic Integrity
- Add `input_sha256` to `doc_meta.json`
- Implement audit trail in `workdir/audit_log.jsonl`
- Add checksum validation for input files

### Phase 5: Testing & Validation (Week 6)
**Goal**: Ensure compliance through comprehensive testing.

#### Step 5.1: Test Corpus Creation
- Create validation corpus with PDF types: digital, scanned, mixed
- Include adversarial cases: complex layouts, handwritten annotations
- Add NIST-PDF-1.7-SUITE and PubLayNet samples

#### Step 5.2: Regression Testing
- Update `regression` command to use v1.3.1 thresholds
- Add format-specific threshold configuration (`regression_thresholds.yaml`)
- Implement failure reporting with detailed metrics

#### Step 5.3: Integration Tests
- Create end-to-end tests for all CLI commands
- Test error conditions and recovery
- Validate schema compliance automatically

---

## 6. Risk Assessment & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| **Surya dependency issues** | High | Medium | Provide clear installation instructions, fallback mode for development |
| **Performance degradation** | Medium | High | Profile critical paths, optimize preprocessing, add caching |
| **Backward compatibility** | Medium | High | Maintain legacy schemas with deprecation warnings |
| **Complexity increase** | Medium | Medium | Modular implementation, thorough documentation |
| **Testing coverage** | High | Low | Implement comprehensive test suite before deployment |

---

## 7. Success Criteria

1. **Mandatory Surya Integration**: All PDF processing uses Surya layout analysis with confidence scores
2. **Complete Schema Compliance**: All output files include required fields per v1.3.1
3. **Comprehensive Error Handling**: All error conditions map to appropriate exit codes (64-77)
4. **Quality Metrics**: OHRBench-inspired metrics implemented and reported
5. **Unified Schema**: `ingestion.jsonl` produced as primary artifact
6. **Resource Safety**: Memory/CPU constraints enforced for PDF processing
7. **Regression Testing**: `regression` command fails appropriately on threshold violations

---

## 8. Recommended Immediate Actions

1. **Update Requirements Alignment**: Clarify whether code should follow v0.1.x or v1.3.1
2. **Prioritize Critical Gaps**: Focus on Surya integration and schema compliance first
3. **Create Validation Suite**: Build test corpus to verify compliance
4. **Documentation Update**: Update README and user documentation with v1.3.1 expectations
5. **Version Strategy**: Consider versioning the implementation (v1.3.1-compliant vs v0.1.x)

---

## 9. Conclusion

The current implementation provides a solid foundation but requires significant work to achieve full v1.3.1 compliance for PDF documents. The proposed 6-week plan addresses critical gaps in priority order, focusing on mandatory requirements first. Success will require careful coordination between engine integration, schema updates, and comprehensive testing.

**Recommendation**: Proceed with Phase 1 immediately to address the most critical compliance issues (Surya integration, OCR preprocessing, schema fields) while maintaining backward compatibility for existing users.
