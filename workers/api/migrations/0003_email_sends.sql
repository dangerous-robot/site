-- One row per confirmation email sent, for the hourly cap. Counting signature
-- rows missed re-sends, which reuse their row. Timestamp only: no address or
-- signature id, so the privacy promise in 0001 still holds.
CREATE TABLE email_sends (
  sent_at TEXT NOT NULL
);
CREATE INDEX email_sends_sent_at ON email_sends (sent_at);

-- Added in 0002 for the old row-counting cap; nothing reads it that way now.
DROP INDEX signatures_created_at;
