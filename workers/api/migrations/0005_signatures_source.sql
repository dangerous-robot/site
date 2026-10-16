-- How a signature was confirmed: the web form's email link, or a message sent to
-- sign@dangerousrobot.org that passed DMARC. Lets the operator list or purge email
-- signatures by domain. Web inserts do not name the column, so the Worker runs the
-- same before and after this migration.
ALTER TABLE signatures ADD COLUMN source TEXT NOT NULL DEFAULT 'web' CHECK (source IN ('web', 'email'));

-- Messages to sign@ acted on per sender domain per UTC day, for the per-domain cap.
-- Counts replies that leave no signature row (unknown petition, no name) too. The
-- domain is stored hashed, so the table is not a readable list of who wrote in;
-- the daily cron deletes past days.
CREATE TABLE email_in_counts (
  day          TEXT NOT NULL,
  domain_hash  TEXT NOT NULL,
  n            INTEGER NOT NULL,
  PRIMARY KEY (day, domain_hash)
) WITHOUT ROWID;
