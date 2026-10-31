-- 057_supplier_relationships.sql — the generalized commercial &
-- corporate relationship evidence ledger (FDCE power-supply chain).
--
-- Design contract (spec):
--   * NOT a supplier/customer lookup — a point-in-time, append-only
--     ledger of relationship OBSERVATIONS. Either end may be
--     anonymous (confidential customer, unnamed supplier base).
--   * relationship_TYPE and STATUS are separate dimensions —
--     'divested' is a lifecycle, 'supplier_confidential' a subtype.
--   * Aggregate disclosures are first-class: Modine's "three
--     significant data-center customers" is real evidence WITHOUT
--     inventing VRT/GEV/ETN identities.
--   * PIT: recorded_at/as_of_date/versioned relationship_id —
--     acquisitions and divestitures must not rewrite history.
--   * design_win_id links to design_wins so the same commercial
--     evidence is never double-counted.
--   * reviewer_status separates curated truth (manual_curation /
--     approved) from extractor output awaiting review.
SELECT pg_advisory_xact_lock(715057);

CREATE TABLE IF NOT EXISTS supplier_relationships (
    id                       bigserial PRIMARY KEY,
    relationship_id          text NOT NULL,      -- logical edge; versions share it
    -- endpoints — either side may be anonymous
    from_symbol              text,               -- NULL = anonymous origin
    from_entity_type         text NOT NULL DEFAULT 'public_company',
                             -- public_company | confidential_supplier |
                             -- anonymous_supplier | subsidiary | private_company
    from_display_label       text,
    to_symbol                text,               -- NULL = anonymous counterparty
    to_entity_type           text NOT NULL DEFAULT 'public_company',
                             -- public_company | confidential_customer |
                             -- customer_group | hyperscaler | utility
    to_display_label         text,
    -- what kind of edge
    relationship_type        text NOT NULL,
                             -- commercial_supply | commercial_customer |
                             -- ownership | acquisition | asset_transfer |
                             -- industry_exposure | commodity_exposure |
                             -- design_win
    relationship_subtype     text,
                             -- supplier_named | supplier_confidential |
                             -- customer_named | customer_confidential |
                             -- owned | acquisition_pending | divested |
                             -- industry_exposure | commodity
    product_id               text,
    product_layer            text,               -- domain layer vocabulary
    -- evidence
    evidence_stage           smallint,           -- 0-5, FDCE E-ladder
    evidence_confidence      smallint,           -- 0-100
    source_type              text,
                             -- company_filing | company_announcement |
                             -- third_party | manual | extractor
    source_id                text,
    verbatim_quote           text,
    publication_date         date,               -- when evidence went public
    source_observation_date  date,               -- when the fact was true
    -- disclosure character
    customer_disclosure      text NOT NULL DEFAULT 'not_applicable',
                             -- named | confidential | aggregate_only |
                             -- not_applicable
    aggregate_customer_count int,
    economic_materiality     text NOT NULL DEFAULT 'unknown',
                             -- material | meaningful | immaterial | unknown
    -- lifecycle
    lifecycle_status         text NOT NULL DEFAULT 'active',
                             -- announced | active | pending | completed |
                             -- terminated | divested | expired | unknown
    valid_from               date,
    valid_to                 date,
    -- provenance (PIT replay)
    recorded_at              timestamptz NOT NULL DEFAULT now(),
    as_of_date               date NOT NULL DEFAULT CURRENT_DATE,
    origin                   text NOT NULL DEFAULT 'extractor',
                             -- manual_curation | extractor |
                             -- company_filing | third_party_source
    reviewer_status          text NOT NULL DEFAULT 'approved',
                             -- approved | extracted | rejected
    design_win_id            bigint REFERENCES design_wins(id),
    note                     text
);

CREATE INDEX IF NOT EXISTS idx_suprel_from
    ON supplier_relationships (from_symbol, as_of_date DESC);
CREATE INDEX IF NOT EXISTS idx_suprel_to
    ON supplier_relationships (to_symbol, as_of_date DESC);
CREATE INDEX IF NOT EXISTS idx_suprel_rid
    ON supplier_relationships (relationship_id, recorded_at DESC);

-- ------------------------------------------------------------------
-- Curated seed ledger — the power-infrastructure evidence map.
-- These are expert-verified facts the extractor cannot reliably
-- produce (ownership changes, confidential disclosures). origin =
-- manual_curation keeps them authoritative over extractor rows.
-- ------------------------------------------------------------------

-- MOD → three CONFIDENTIAL data-center customers. Real evidence;
-- customer identities are NOT invented.
INSERT INTO supplier_relationships
 (relationship_id, from_symbol, to_symbol, to_entity_type,
  to_display_label, relationship_type, relationship_subtype,
  product_id, product_layer,
  evidence_stage, evidence_confidence, source_type,
  verbatim_quote, publication_date,
  customer_disclosure, aggregate_customer_count,
  economic_materiality, lifecycle_status,
  origin, reviewer_status, note)
VALUES
 ('rel_mod_dc_cooling', 'MOD', NULL, 'confidential_customer',
  'confidential_data_center_customers', 'commercial_supply',
  'customer_confidential', 'data_center_cooling',
  'thermal_heat_exchangers',
  4, 85, 'company_filing',
  'three significant data-center customers under confidentiality '
  'agreements', '2026-05-15',
  'confidential', 3,
  'meaningful', 'active',
  'manual_curation', 'approved',
  'FY26 10-K — customers real but unnamed; do NOT attribute to '
  'VRT/GEV/ETN. Same filing: key DC-cooling components in short '
  'supply — lead_time_pressure evidence.');

-- GEV → Prolec GE: 100% ownership COMPLETED Feb 2026 — internal
-- capability, not an independent supplier.
INSERT INTO supplier_relationships
 (relationship_id, from_symbol, to_symbol, to_entity_type,
  to_display_label, relationship_type, relationship_subtype,
  product_id, product_layer,
  evidence_stage, evidence_confidence, source_type,
  publication_date, source_observation_date,
  customer_disclosure, economic_materiality,
  lifecycle_status, valid_from,
  origin, reviewer_status, note)
VALUES
 ('rel_gev_prolec', 'GEV', 'PROLEC', 'subsidiary',
  'Prolec GE', 'ownership', 'owned', 'transformers',
  'grid_equipment',
  5, 100, 'company_announcement',
  '2026-02-03', '2026-02-03',
  'not_applicable', 'material',
  'completed', '2026-02-01',
  'manual_curation', 'approved',
  'Remaining 50% acquired Feb 2026 — Prolec is internal '
  'transformer/grid capability, not an investable supplier.');

-- GEV → Trench Group: SIGNED Oct 2026, closes late 2027 — pending,
-- NOT yet owned.
INSERT INTO supplier_relationships
 (relationship_id, from_symbol, to_symbol, to_entity_type,
  to_display_label, relationship_type, relationship_subtype,
  product_id, product_layer,
  evidence_stage, evidence_confidence, source_type,
  publication_date, source_observation_date,
  customer_disclosure, economic_materiality,
  lifecycle_status, valid_from,
  origin, reviewer_status, note)
VALUES
 ('rel_gev_trench', 'GEV', 'TRENCH', 'private_company',
  'Trench Group', 'acquisition', 'acquisition_pending',
  'hv_bushings_transformers_coils', 'grid_components',
  4, 95, 'company_announcement',
  '2026-10-15', '2026-10-15',
  'not_applicable', 'material',
  'pending', NULL,
  'manual_curation', 'approved',
  'Signed Oct 2026, expected close late 2027 — pending means NOT '
  'owned; treat Trench as independent until completed.');

-- WWD → GEV (edge 1 of 2): asset_transfer — the dedicated
-- heavy-duty gas-turbine combustion-parts business went TO GEV in
-- 2024. It is NOT a WWD product anymore.
INSERT INTO supplier_relationships
 (relationship_id, from_symbol, to_symbol, to_entity_type,
  to_display_label, relationship_type, relationship_subtype,
  product_id, product_layer,
  evidence_stage, evidence_confidence, source_type,
  publication_date, source_observation_date,
  customer_disclosure, economic_materiality,
  lifecycle_status, valid_to,
  origin, reviewer_status, note)
VALUES
 ('rel_wwd_gev_divest', 'WWD', 'GEV', 'public_company',
  'GE Vernova', 'asset_transfer', 'divested',
  'hdt_combustion_parts', 'turbine_controls',
  4, 95, 'company_announcement',
  '2024-06-01', '2024-06-01',
  'not_applicable', 'material',
  'divested', '2024-06-01',
  'manual_curation', 'approved',
  'Greenville heavy-duty combustion-parts business transferred to '
  'GEV 2024 — do NOT attribute it to WWD revenue today.');

-- WWD → GEV (edge 2 of 2): commercial_supply — a SEPARATE ongoing
-- relationship: GEV is a ≥10% Industrial-segment customer of WWD.
-- The divestiture did NOT end every WWD/GEV commercial tie.
INSERT INTO supplier_relationships
 (relationship_id, from_symbol, to_symbol, to_entity_type,
  to_display_label, relationship_type, relationship_subtype,
  product_id, product_layer,
  evidence_stage, evidence_confidence, source_type,
  verbatim_quote, publication_date, source_observation_date,
  customer_disclosure, economic_materiality,
  lifecycle_status, valid_from,
  origin, reviewer_status, note)
VALUES
 ('rel_wwd_gev_customer', 'WWD', 'GEV', 'public_company',
  'GE Vernova', 'commercial_supply', 'customer_named',
  'industrial_controls', 'turbine_controls',
  4, 90, 'company_filing',
  'GE Vernova is a customer accounting for at least 10% of '
  'Industrial segment sales', '2025-11-15', '2025-09-30',
  'named', 'material',
  'active', NULL,
  'manual_curation', 'approved',
  'FY25 10-K — distinct from the divested combustion-parts '
  'business; the transfer did not end the commercial tie.');

-- BE → CONFIDENTIAL specialty-material supplier base. Bloom
-- disclosed the materials (specialty metals, steel alloys,
-- electronic components, rare-earth-dependent) but NOT the
-- suppliers — anonymous from-side.
INSERT INTO supplier_relationships
 (relationship_id, from_symbol, from_entity_type, from_display_label,
  to_symbol, to_entity_type, to_display_label,
  relationship_type, relationship_subtype,
  product_id, product_layer,
  evidence_stage, evidence_confidence, source_type,
  verbatim_quote, publication_date,
  customer_disclosure, economic_materiality,
  lifecycle_status,
  origin, reviewer_status, note)
VALUES
 ('rel_be_specialty_suppliers', NULL, 'confidential_supplier',
  'confidential_specialty_material_suppliers',
  'BE', 'public_company', 'Bloom Energy',
  'commercial_supply', 'supplier_confidential',
  'fuel_cell_specialty_materials', 'specialty_alloys',
  3, 70, 'company_filing',
  'specialty metals, steel alloys, electronic components and '
  'rare-earth-dependent materials', '2025-04-30',
  'confidential', 'meaningful',
  'active',
  'manual_curation', 'approved',
  '10-K disclosed materials classes, not names — investigate '
  'ATI/CRS only as industry exposure, never as confirmed BE '
  'suppliers.');

-- FCX → copper/materials ecosystem: commodity exposure to the whole
-- electrical-equipment buildout, NOT a confirmed OEM supply edge.
INSERT INTO supplier_relationships
 (relationship_id, from_symbol, to_symbol, to_entity_type,
  to_display_label, relationship_type, relationship_subtype,
  product_id, product_layer,
  evidence_stage, evidence_confidence, source_type,
  publication_date, customer_disclosure,
  economic_materiality, lifecycle_status,
  origin, reviewer_status, note)
VALUES
 ('rel_fcx_copper', 'FCX', NULL, 'customer_group',
  'electrical_equipment_ecosystem', 'commodity_exposure',
  'commodity', 'copper', 'copper_materials',
  3, 60, 'manual',
  '2026-10-31', 'not_applicable',
  'meaningful', 'active',
  'manual_curation', 'approved',
  'Copper demand rises with grid/DC construction — a commodity '
  'demand link, never a confirmed sale to a named OEM.');

-- APH → broad interconnect capability: industry exposure. Broad
-- product-market coverage is NOT four confirmed OEM customers.
INSERT INTO supplier_relationships
 (relationship_id, from_symbol, to_symbol, to_entity_type,
  to_display_label, relationship_type, relationship_subtype,
  product_id, product_layer,
  evidence_stage, evidence_confidence, source_type,
  publication_date, customer_disclosure,
  economic_materiality, lifecycle_status,
  origin, reviewer_status, note)
VALUES
 ('rel_aph_interconnect', 'APH', NULL, 'customer_group',
  'datacenter_power_oem_ecosystem', 'industry_exposure',
  'industry_exposure', 'hv_interconnect_busbar',
  'high_voltage_connectors',
  3, 65, 'manual',
  '2026-10-31', 'not_applicable',
  'meaningful', 'active',
  'manual_curation', 'approved',
  'Broad HV-connector/busbar capability — industry-level exposure '
  'only; confirmed OEM edges require named evidence.');
