# ADR-001: Minimal metadata schema for PACS storage

Date: 2025-12-31

Status: Accepted

## Context

The PACS server needs to store DICOM image metadata to support queries and tracking without reading DICOM files from disk.

We needed to decide how much DICOM metadata to extract and store in the database versus what can remain only in the DICOM files themselves.

**Requirements:**
- Track which images have been stored
- Associate images with patients and procedures
- Support basic queries for verification and auditing
- Track where files came from (source AET)
- Work on a 'minimum viable' basis

## Decision

We will implement a **minimal metadata schema** that stores only essential fields required for current functionality:

**Fields included:**
1. `sop_instance_uid` - Primary key, uniquely identifies the image
2. `storage_path` - Relative path to DICOM file
3. `file_size` - File size in bytes
4. `storage_hash` - SHA256 hash for integrity verification
5. `patient_id` - Patient identifier (NHS number from worklist)
6. `patient_name` - Patient name in DICOM format
7. `accession_number` - Links image to procedure/appointment
8. `source_aet` - Application Entity Title of sender (for audit trail)
9. `status` - Storage status
10. `created_at` - Timestamp when image was received

**Fields deferred:**
- Study/Series identifiers (study_instance_uid, series_instance_uid)
- Study/Series descriptions and numbers
- Modality type
- Image dimensions (rows, columns)
- Anatomical details (view_position, laterality)
- Dose information (organ_dose, entrance_dose_in_mgy, kvp, exposure_in_uas)
- Equipment details (anode_target_material, filter_material, filter_thickness)
- Transfer syntax and SOP class information
- Thumbnail tracking

These deferred fields can be extracted from DICOM files on-demand if needed.

## Consequences

### Positive Consequences

- **Simpler codebase:** Fewer fields to extract, validate, and test in C-STORE handler
- **Easier maintenance:** Schema is straightforward to understand and modify
- **Clearer focus:** Schema reflects actual current requirements, not speculative future needs

### Negative Consequences

- **Limited query capabilities:** Cannot filter by modality, study description, view position, etc. without reading DICOM files
- **Schema evolution required:** Adding new query requirements will require schema migration
- **DICOM hierarchy invisible:** Cannot easily group images by study/series without file reads
