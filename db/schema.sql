CREATE TABLE IF NOT EXISTS coffeeshops (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  slug        TEXT UNIQUE NOT NULL,
  name        TEXT NOT NULL,
  address     TEXT,
  city        TEXT DEFAULT 'Amsterdam',
  created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS menu_snapshots (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  coffeeshop_id   INTEGER REFERENCES coffeeshops(id),
  image_url       TEXT NOT NULL,
  menu_date       TEXT,
  contributor     TEXT,
  scraped_at      TIMESTAMP NOT NULL,
  processed_at    TIMESTAMP,
  raw_json        TEXT,
  is_active       BOOLEAN DEFAULT 1,
  UNIQUE(coffeeshop_id, image_url)
);

CREATE TABLE IF NOT EXISTS strains (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  coffeeshop_id   INTEGER REFERENCES coffeeshops(id),
  snapshot_id     INTEGER REFERENCES menu_snapshots(id),
  name            TEXT NOT NULL,
  name_normalized TEXT NOT NULL,
  category        TEXT NOT NULL CHECK(category IN (
                    'sativa','indica','hybrid','hash','edible','pre-roll','other'
                  )),
  price_per_gram  REAL,
  notes           TEXT,
  created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_strains_name     ON strains(name_normalized);
CREATE INDEX IF NOT EXISTS idx_strains_category ON strains(category);
CREATE INDEX IF NOT EXISTS idx_strains_shop     ON strains(coffeeshop_id);

CREATE TABLE IF NOT EXISTS scrape_log (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at    TIMESTAMP,
  finished_at   TIMESTAMP,
  shops_checked INTEGER,
  shops_updated INTEGER,
  errors        TEXT
);
