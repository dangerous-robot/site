-- The hourly email cap counts rows by created_at on every sign POST; without
-- this index that is a full scan of signatures across all petitions.
CREATE INDEX signatures_created_at ON signatures (created_at);
