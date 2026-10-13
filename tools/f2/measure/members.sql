-- Which entities each count measure counts, and in which provinces.
-- One row per (measure, entity, province); province_code is NULL when the entity has no qualifying place.
-- A national value is COUNT(DISTINCT entity_id); a province value counts the entities with a row for it.

CREATE OR REPLACE TABLE measure_members AS
WITH
member AS (SELECT entity, entity_id, source, record_id FROM entity_members),

-- Innovations: provinces where the innovation is used.
innovation_province AS (
    SELECT DISTINCT m.entity_id, p.province_code
    FROM member m JOIN innovation_places p USING (source, record_id)
    WHERE m.entity = 'innovation' AND p.role = 'use' AND p.province_code IS NOT NULL),
innovation_counted AS (
    SELECT DISTINCT 'C04_LISTED' AS measure_id, entity_id FROM member WHERE entity = 'innovation'
    UNION ALL
    -- K04: at least one record states technology readiness level 8 or 9
    SELECT DISTINCT 'K04', m.entity_id
    FROM member m JOIN innovation_readiness r USING (source, record_id)
    WHERE m.entity = 'innovation' AND r.scale = 'TRL' AND r.level >= 8),

-- People
person_row AS (
    SELECT m.entity_id, p.* FROM member m JOIN people p USING (source, record_id) WHERE m.entity = 'person'),
complete_assessment AS (  -- a person record with start and current levels for all three dimensions
    SELECT source, person_record_id, bool_or(current_level > start_level) AS increased
    FROM assessments WHERE start_level IS NOT NULL AND current_level IS NOT NULL
    GROUP BY ALL HAVING count(DISTINCT dimension) = 3),
person_counted AS (
    -- C02: community innovators (iCommunity) and inventors (AppTech MRU, and inventors reviewers found);
    -- a place whose map point disagrees with its written name is not used
    SELECT DISTINCT 'C02_COMMUNITY' AS measure_id, entity_id,
           CASE WHEN NOT contains(coalesce(geo_note, ''), 'geocode_disagrees') THEN province_code END AS province_code
    FROM person_row WHERE role IN ('community_innovator', 'inventor', 'inventor_and_developer')
    UNION ALL
    SELECT DISTINCT 'C08_ASSESSED_PEOPLE', p.entity_id, NULL
    FROM person_row p JOIN complete_assessment a ON a.source = p.source AND a.person_record_id = p.record_id
    UNION ALL
    SELECT DISTINCT 'C08_INCREASED_PEOPLE', p.entity_id, NULL
    FROM person_row p JOIN complete_assessment a ON a.source = p.source AND a.person_record_id = p.record_id
    WHERE a.increased),

-- Cultural records: K12 = Cultural Map subjects (all categories); K01B = cultural areas (Cultural Map
-- cultural spaces and AtLocal programme areas).
cultural_row AS (
    SELECT m.entity_id, c.* FROM member m JOIN cultural_records c USING (source, record_id) WHERE m.entity = 'cultural_record'),
cultural_counted AS (
    SELECT DISTINCT 'K12' AS measure_id, entity_id, province_code FROM cultural_row WHERE source = 'cultural_map'
    UNION ALL
    SELECT DISTINCT 'K01B', entity_id, province_code FROM cultural_row WHERE category IN ('CS', 'area')),

-- Activities: provinces of the venues (online delivery has none).
activity_counted AS (
    SELECT DISTINCT 'K03' AS measure_id, m.entity_id,
           CASE WHEN v.venue->>'role' <> 'online_delivery' THEN v.venue->>'province_code' END AS province_code
    FROM member m JOIN activities a USING (source, record_id)
    LEFT JOIN LATERAL (SELECT unnest(CAST(a.venues AS JSON[])) AS venue) v ON true
    WHERE m.entity = 'activity'),

-- Businesses (K05) and the Learning area-based directory's participating businesses (C08).
operator_row AS (
    SELECT m.entity_id, o.* FROM member m JOIN operators o USING (source, record_id) WHERE m.entity = 'operator'),
operator_counted AS (
    SELECT DISTINCT 'K05' AS measure_id, entity_id, province_code FROM operator_row
    UNION ALL
    SELECT DISTINCT 'C08_PARTICIPATING', entity_id, province_code FROM operator_row WHERE source = 'learning_area_based'),

-- Offerings (K07 counts product families). A listing without a name is not an offering; an offering with
-- a record in counting_exclusions (a broad product range used as evidence for other families) is not counted.
excluded_offering AS (
    SELECT DISTINCT m.entity_id FROM member m JOIN counting_exclusions x USING (source, record_id)
    WHERE m.entity = 'offering' AND x.measure_id = 'K07'),
offering_counted AS (
    SELECT DISTINCT 'K07' AS measure_id, f.entity_id, o.province_code
    FROM member f JOIN offerings o USING (source, record_id)
    JOIN member m ON m.entity = 'offering' AND m.source = f.source AND m.record_id = f.record_id
    WHERE f.entity = 'offering_family' AND o.name <> '' AND m.entity_id NOT IN (SELECT entity_id FROM excluded_offering)
    UNION ALL
    -- a family backed by an excluded range listing takes the listing's place
    SELECT DISTINCT 'K07', f.entity_id, o.province_code
    FROM member f JOIN counting_place_from x ON x.measure_id = 'K07' AND x.source = f.source AND x.record_id = f.record_id
    JOIN offerings o ON o.source = x.place_source AND o.record_id = x.place_record_id
    WHERE f.entity = 'offering_family'),

counted AS (
    SELECT measure_id, 'innovation' AS entity, entity_id, province_code
    FROM innovation_counted LEFT JOIN innovation_province USING (entity_id)
    UNION ALL SELECT measure_id, 'person', entity_id, province_code FROM person_counted
    UNION ALL SELECT measure_id, 'cultural_record', entity_id, province_code FROM cultural_counted
    UNION ALL SELECT measure_id, 'activity', entity_id, province_code FROM activity_counted
    UNION ALL SELECT measure_id, 'operator', entity_id, province_code FROM operator_counted
    UNION ALL SELECT measure_id, 'offering_family', entity_id, province_code FROM offering_counted)

-- an entity with a province does not also keep a "no province" row
SELECT DISTINCT measure_id, entity, entity_id, province_code FROM counted c
WHERE province_code IS NOT NULL
   OR NOT EXISTS (SELECT 1 FROM counted d WHERE d.measure_id = c.measure_id AND d.entity_id = c.entity_id
                                            AND d.province_code IS NOT NULL);

-- K01A: provinces with programme evidence of any kind: where innovations are used, cultural records,
-- activity venues, participating businesses, community innovators, product and business listings, and
-- provinces where the Learning dashboard reports businesses.
INSERT INTO measure_members
SELECT DISTINCT 'K01A', 'province', province_code, province_code FROM (
    SELECT province_code FROM measure_members WHERE measure_id IN ('C04_LISTED', 'K12', 'K01B', 'K03', 'C08_PARTICIPATING')
    UNION ALL SELECT province_code FROM people WHERE role = 'community_innovator'
    UNION ALL SELECT province_code FROM offerings WHERE kind = 'listed'
    UNION ALL SELECT province_code FROM operators WHERE kind = 'listed' AND source = 'atlocal'
    UNION ALL SELECT province_code FROM reported_figures WHERE metric = 'businesses_by_province' AND value > 0)
WHERE province_code IS NOT NULL;
