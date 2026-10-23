-- How a signature was confirmed: the web form's email link, or a message sent to
-- sign@dangerousrobot.org that passed DMARC. Lets the operator list or purge email
-- signatures by domain. Web inserts do not name the column, so the Worker runs the
-- same before and after this migration.
ALTER TABLE signatures ADD COLUMN source TEXT NOT NULL DEFAULT 'web' CHECK (source IN ('web', 'email'));

-- Messages to sign@ acted on per UTC day, per sender address and per registered
-- domain, for the caps. Counts replies that leave no signature row (unknown petition,
-- no name) too. Keys are SHA-256 hashes, so the table holds no address or domain in
-- plain text (a guessed domain can still be checked against it); the daily cron
-- deletes past days.
CREATE TABLE email_in_counts (
  day       TEXT NOT NULL,
  key_hash  TEXT NOT NULL,
  n         INTEGER NOT NULL,
  PRIMARY KEY (day, key_hash)
) WITHOUT ROWID;
