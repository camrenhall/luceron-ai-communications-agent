-- Migration: Remove case_id column entirely from agent_conversations table
-- This achieves complete separation of concerns between conversations and cases

-- Step 1: Drop any indexes that reference case_id column
DROP INDEX IF EXISTS idx_agent_conversations_case_id_nullable;
DROP INDEX IF EXISTS idx_agent_conversations_no_case;
DROP INDEX IF EXISTS idx_agent_conversations_case_id;

-- Step 2: Drop the foreign key constraint
ALTER TABLE public.agent_conversations 
DROP CONSTRAINT IF EXISTS agent_conversations_case_id_fkey;

-- Step 3: Drop the case_id column entirely
ALTER TABLE public.agent_conversations 
DROP COLUMN IF EXISTS case_id;

-- Verification queries to run after migration:
-- \d agent_conversations; -- Should show table structure without case_id column
-- SELECT COUNT(*) FROM agent_conversations; -- Should show all existing conversations