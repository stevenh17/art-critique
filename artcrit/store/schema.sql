-- Append-only: rows are inserted, never changed. Later facts arrive as new rows.
CREATE TABLE IF NOT EXISTS drawings (
  id INTEGER PRIMARY KEY,
  photo_path TEXT NOT NULL,
  photo_crop TEXT NOT NULL,          -- JSON [x0, y0, x1, y1]
  photo_source_url TEXT NOT NULL,
  photo_license TEXT NOT NULL,
  publish INTEGER NOT NULL,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE TABLE IF NOT EXISTS submissions (
  id INTEGER PRIMARY KEY,
  drawing_id INTEGER NOT NULL REFERENCES drawings(id),
  version INTEGER NOT NULL,
  parent_id INTEGER REFERENCES submissions(id),
  original_path TEXT NOT NULL,
  normalized_path TEXT NOT NULL,
  corners TEXT NOT NULL,             -- JSON [[x, y] x4], TL TR BR BL
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE TABLE IF NOT EXISTS submission_status (
  id INTEGER PRIMARY KEY,
  submission_id INTEGER NOT NULL REFERENCES submissions(id),
  status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'done', 'failed', 'limit')),
  detail TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE TABLE IF NOT EXISTS critiques (
  id INTEGER PRIMARY KEY,
  submission_id INTEGER NOT NULL REFERENCES submissions(id),
  critique_json TEXT NOT NULL,
  tool_trace TEXT NOT NULL,
  model TEXT NOT NULL,
  lessons_sha TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE TABLE IF NOT EXISTS issues (
  id INTEGER PRIMARY KEY,
  critique_id INTEGER NOT NULL REFERENCES critiques(id),
  submission_id INTEGER NOT NULL REFERENCES submissions(id),
  position INTEGER NOT NULL,
  category TEXT NOT NULL,
  title TEXT NOT NULL,
  instruction TEXT NOT NULL,
  drawing_cells TEXT NOT NULL,       -- JSON list
  photo_cells TEXT NOT NULL,         -- JSON list
  lesson_refs TEXT NOT NULL          -- JSON list
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY,
  type TEXT NOT NULL,
  issue_id INTEGER REFERENCES issues(id),
  submission_id INTEGER REFERENCES submissions(id),
  payload TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
