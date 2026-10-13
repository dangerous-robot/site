-- Whether the signer ticked "Send me occasional email updates about this
-- campaign". The update list is confirmed rows with 1 (double opt-in), and the
-- closing cleanup keeps those emails until the signer opts out.
ALTER TABLE signatures ADD COLUMN updates_consent INTEGER NOT NULL DEFAULT 0 CHECK (updates_consent IN (0, 1));
