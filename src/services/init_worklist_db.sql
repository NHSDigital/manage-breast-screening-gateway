-- Modality Worklist SQLite Schema
--
-- This schema stores DICOM worklist items that are:
-- - Created by the relay listener when appointments are sent from the web app
-- - Queried by the MWL server in response to C-FIND requests from modalities
-- - Updated via MPPS when procedures start/complete

-- Main worklist items table
CREATE TABLE IF NOT EXISTS worklist_items (
    -- Unique identifier for the scheduled procedure
    accession_number TEXT PRIMARY KEY,

    -- Patient demographics
    patient_id TEXT NOT NULL,
    patient_name TEXT NOT NULL,              -- DICOM format: FAMILY^GIVEN
    patient_birth_date TEXT NOT NULL,        -- YYYYMMDD format
    patient_sex TEXT,                        -- M/F/O

    -- Scheduling information
    scheduled_date TEXT NOT NULL,            -- YYYYMMDD format in UTC
    scheduled_time TEXT NOT NULL,            -- HHMMSS format in UTC
    modality TEXT NOT NULL,                  -- e.g., MG for mammography

    -- Procedure details
    study_description TEXT,
    procedure_code TEXT,

    -- Status tracking
    status TEXT DEFAULT 'SCHEDULED' CHECK(status IN ('SCHEDULED', 'IN_PROGRESS', 'COMPLETED', 'DISCONTINUED')),

    -- DICOM identifiers
    study_instance_uid TEXT,
    mpps_instance_uid TEXT, -- Modality Performed Procedure Step (MPPS) UID

    -- Audit trail
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

    -- Link to source message from relay listener
    source_message_id TEXT
);

-- Index for the most common query pattern (MWL C-FIND by modality and date)
CREATE INDEX IF NOT EXISTS idx_worklist_date_modality
ON worklist_items(scheduled_date, modality);

-- Index for status queries (finding in-progress procedures, etc.)
CREATE INDEX IF NOT EXISTS idx_worklist_status
ON worklist_items(status);

-- Index for MPPS lookups by study instance UID
CREATE INDEX IF NOT EXISTS idx_worklist_study_uid
ON worklist_items(study_instance_uid);

-- Index for patient lookups
CREATE INDEX IF NOT EXISTS idx_worklist_patient_id
ON worklist_items(patient_id);

-- Index for MPPS instance UID lookups
CREATE INDEX IF NOT EXISTS idx_worklist_mpps_instance_uid
ON worklist_items(mpps_instance_uid);

