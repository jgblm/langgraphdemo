-- Database initialization script for LangGraph Marketing Analysis POC
-- Run this script to initialize all database tables before starting the application
-- Note: This is based on langgraph-checkpoint-postgres v2.0.25

-- ============================================
-- Application Tables
-- ============================================

-- Create task status enum type
DO $$ BEGIN
    CREATE TYPE taskstatus AS ENUM ('pending', 'processing', 'tags_completed', 'persona_completed', 'completed', 'failed');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Analysis tasks table: stores marketing analysis tasks
CREATE TABLE IF NOT EXISTS analysis_tasks (
    id VARCHAR(36) PRIMARY KEY,
    brand VARCHAR(255) NOT NULL,
    region VARCHAR(255) NOT NULL,
    status taskstatus NOT NULL DEFAULT 'pending',
    tags JSONB,
    tags_raw TEXT,
    persona JSONB,
    persona_raw TEXT,
    scenes JSONB,
    scenes_raw TEXT,
    error_message TEXT,
    error_step VARCHAR(50),
    checkpoint_step VARCHAR(50) DEFAULT 'pending',
    langsmith_trace_id VARCHAR(255),
    langsmith_observation_ids JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_analysis_tasks_status ON analysis_tasks(status);
CREATE INDEX IF NOT EXISTS idx_analysis_tasks_created_at ON analysis_tasks(created_at);
CREATE INDEX IF NOT EXISTS idx_analysis_tasks_brand ON analysis_tasks(brand);

-- ============================================
-- LangGraph AsyncPostgresSaver Checkpoint Tables
-- (Based on langgraph-checkpoint-postgres MIGRATIONS)
-- ============================================

-- Migration tracking table (Migration 0)
CREATE TABLE IF NOT EXISTS checkpoint_migrations (
    v INTEGER PRIMARY KEY
);

-- Checkpoints table (Migration 1): stores the core checkpoint data
CREATE TABLE IF NOT EXISTS checkpoints (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    parent_checkpoint_id TEXT,
    type TEXT,
    checkpoint JSONB NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);

-- Checkpoint blobs table (Migration 2): stores channel data
CREATE TABLE IF NOT EXISTS checkpoint_blobs (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    channel TEXT NOT NULL,
    version TEXT NOT NULL,
    type TEXT NOT NULL,
    blob BYTEA,
    PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
);

-- Checkpoint writes table (Migration 3, updated 9): stores pending write operations
CREATE TABLE IF NOT EXISTS checkpoint_writes (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    idx INTEGER NOT NULL,
    channel TEXT NOT NULL,
    type TEXT,
    blob BYTEA NOT NULL,
    task_path TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);

-- Indexes for checkpoint tables (Migrations 6-8)
CREATE INDEX IF NOT EXISTS checkpoints_thread_id_idx ON checkpoints(thread_id);
CREATE INDEX IF NOT EXISTS checkpoint_blobs_thread_id_idx ON checkpoint_blobs(thread_id);
CREATE INDEX IF NOT EXISTS checkpoint_writes_thread_id_idx ON checkpoint_writes(thread_id);
