-- Migration 0010: Wall-Clock Premise Expiry (valid_until) for Grounded Facts & KG Edges
-- Separates forward-looking TTL expiration (valid_until <= now, Belnap BOT when unreplaced)
-- from event-driven supersession/retraction (valid_to set by supersede()).

ALTER TABLE memories ADD COLUMN valid_until REAL;
CREATE INDEX IF NOT EXISTS ix_mem_valid_until ON memories(valid_until);

ALTER TABLE kg_edges ADD COLUMN valid_until REAL;
CREATE INDEX IF NOT EXISTS ix_edge_valid_until ON kg_edges(s, p, valid_until);

