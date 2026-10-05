-- Petitions and their signatures. Deliberately no IP, user agent or free-text
-- columns: the privacy copy on the site promises name, email and consent only.

CREATE TABLE petitions (
  slug       TEXT PRIMARY KEY,
  title      TEXT NOT NULL,
  post_url   TEXT NOT NULL,
  status     TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
  opened_at  TEXT NOT NULL,
  closed_at  TEXT
);

CREATE TABLE signatures (
  id               INTEGER PRIMARY KEY,
  petition_slug    TEXT NOT NULL REFERENCES petitions (slug),
  name             TEXT NOT NULL,
  -- Lowercased. Nulled by the daily cron once the petition closes.
  email            TEXT,
  display_consent  INTEGER NOT NULL DEFAULT 0 CHECK (display_consent IN (0, 1)),
  created_at       TEXT NOT NULL,
  confirmed_at     TEXT,
  token_hash       TEXT NOT NULL UNIQUE
);

-- One signature per address per petition. NULL emails (closed petitions) do
-- not collide, since SQLite treats NULLs as distinct in unique indexes.
CREATE UNIQUE INDEX signatures_petition_email ON signatures (petition_slug, email);
CREATE INDEX signatures_petition_confirmed ON signatures (petition_slug, confirmed_at);
