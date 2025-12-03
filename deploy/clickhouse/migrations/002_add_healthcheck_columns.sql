-- Add healthcheck-related columns to docker_containers table

ALTER TABLE docker_containers 
ADD COLUMN IF NOT EXISTS health_status String DEFAULT 'none',
ADD COLUMN IF NOT EXISTS health_test String DEFAULT '',
ADD COLUMN IF NOT EXISTS failing_streak UInt32 DEFAULT 0,
ADD COLUMN IF NOT EXISTS last_health_log String DEFAULT '',
ADD COLUMN IF NOT EXISTS hostname String DEFAULT '';

