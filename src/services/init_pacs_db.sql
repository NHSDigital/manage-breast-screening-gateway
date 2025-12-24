-- PACS Database Schema
-- Stores metadata and file paths for DICOM images

-- Main table for stored DICOM instances
CREATE TABLE IF NOT EXISTS stored_instances (
    -- Primary key: SOP Instance UID
    sop_instance_uid TEXT PRIMARY KEY,

    storage_path TEXT NOT NULL,           -- Relative path from storage root
    file_size INTEGER NOT NULL,           -- File size in bytes
    storage_hash TEXT NOT NULL,           -- Hash for file integrity checks

    patient_id TEXT,
    patient_name TEXT,

    accession_number TEXT,                -- Link to worklist

    status TEXT DEFAULT 'STORED' CHECK(status IN ('STORED', 'ARCHIVED', 'DELETED')),

    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    source_aet TEXT,                      -- AE Title of sender

    UNIQUE(storage_path)
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_patient_id ON stored_instances(patient_id);
CREATE INDEX IF NOT EXISTS idx_accession_number ON stored_instances(accession_number);
CREATE INDEX IF NOT EXISTS idx_created_at ON stored_instances(created_at);
CREATE INDEX IF NOT EXISTS idx_storage_hash ON stored_instances(storage_hash);
