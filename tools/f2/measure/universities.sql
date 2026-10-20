-- Which university each counted innovation, community innovator and business belongs to, as the sources state it.
-- One row per (measure, entity, university, source). An entity the sources tie to two universities counts in both,
-- so the universities' counts do not add up to the national value.

CREATE OR REPLACE TABLE university_members AS
WITH
counted AS (
    SELECT DISTINCT measure_id, entity, entity_id FROM measure_members
    WHERE measure_id IN ('C04_LISTED', 'K04', 'C02_COMMUNITY', 'K05')),
linked_innovation AS (  -- a business a reviewer found named in an innovation's text
    SELECT source, record_id, unnest(CAST(details->'innovation_upstream_ids' AS VARCHAR[])) AS upstream_id
    FROM operators),
stated AS (
    -- innovations: the institution the listing names
    SELECT 'innovation' AS entity, source, record_id, institution AS raw FROM innovations
    UNION ALL
    -- community innovators and inventors: the institution of their project or listing, not their own employer
    SELECT 'person', source, record_id, institution FROM people
    WHERE role IN ('community_innovator', 'inventor', 'inventor_and_developer')
    UNION ALL
    -- businesses: the Learning area-based research unit, or the institution of the innovation that names them
    SELECT 'operator', source, record_id, details->>'research_unit' FROM operators WHERE source = 'learning_area_based'
    UNION ALL
    SELECT 'operator', l.source, l.record_id, i.institution
    FROM linked_innovation l JOIN innovations i ON i.source = l.source AND i.upstream_id = l.upstream_id)
SELECT DISTINCT c.measure_id, c.entity, c.entity_id, n.university, n.university_group, s.source
FROM counted c
JOIN entity_members m ON m.entity = c.entity AND m.entity_id = c.entity_id
JOIN stated s ON s.entity = m.entity AND s.source = m.source AND s.record_id = m.record_id
JOIN institution_names n ON n.raw = s.raw;
