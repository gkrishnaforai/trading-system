-- 075: Focus book — a conviction bucket for names watched on their own
-- merits, independent of the generic screens. A daily scan ingests
-- company-specific developments (press releases, contracts/design wins,
-- product/roadmap events, analyst actions, estimate moves) and scores
-- each by materiality so the board can surface "something changed at
-- this company" the day it happens.

CREATE TABLE IF NOT EXISTS focus_members (
    symbol          VARCHAR(10) PRIMARY KEY,
    thesis          TEXT,                        -- one-line conviction thesis
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    added_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS focus_events (
    id              BIGSERIAL PRIMARY KEY,
    symbol          VARCHAR(10) NOT NULL,
    source          VARCHAR(30) NOT NULL,        -- press_release/news/grade/price_target/estimate
    external_id     VARCHAR(255),                -- provider id or title hash
    event_type      VARCHAR(30) NOT NULL,        -- contract/design_win/product/partnership/
                                                 -- capacity/backlog/guidance/analyst/other
    materiality     INT NOT NULL DEFAULT 1,      -- 1-5: 4-5 = move-thesis events
    title           TEXT NOT NULL,
    summary         TEXT,
    url             TEXT,
    published_at    TIMESTAMPTZ,
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw             JSONB,
    UNIQUE (symbol, source, external_id)
);

CREATE INDEX IF NOT EXISTS focus_events_symbol ON focus_events(symbol);
CREATE INDEX IF NOT EXISTS focus_events_pub    ON focus_events(published_at DESC);
CREATE INDEX IF NOT EXISTS focus_events_mat    ON focus_events(materiality DESC);

-- Seeds: the AI-interconnect conviction book
INSERT INTO focus_members (symbol, thesis) VALUES
 ('CRDO', 'AI datacenter AEC/DSP connectivity — hyperscaler design wins'),
 ('ALAB', 'PCIe/CXL retimers + fabric — AI rack connectivity share gains'),
 ('COHR', 'Optical transceivers/lasers — 800G/1.6T datacom ramp'),
 ('LIGHT','Laser/indium-phosphide components — cloud & AI optics supply')
ON CONFLICT (symbol) DO NOTHING;
