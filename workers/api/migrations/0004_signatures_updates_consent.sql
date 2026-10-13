-- Whether the signer ticked "Send me occasional email updates about this
-- campaign".
ALTER TABLE signatures ADD COLUMN updates_consent INTEGER NOT NULL DEFAULT 0 CHECK (updates_consent IN (0, 1));

-- Who may be sent updates: ticked the box and confirmed (double opt-in). The
-- closing cleanup keeps these addresses and `inv petition-emails` reads them,
-- so the rule lives here once.
CREATE VIEW update_recipients AS
  SELECT * FROM signatures WHERE confirmed_at IS NOT NULL AND updates_consent = 1;
