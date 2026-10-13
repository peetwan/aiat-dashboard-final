-- Measures that are totals a source publishes (dashboards), kept as stated, with the parts they add up from.
-- One row per part; a measure's national value is the sum of its parts within one breakdown, divided by
-- the measure's divisor (THB -> million THB).

CREATE OR REPLACE TABLE measure_values AS
WITH f AS (SELECT * FROM reported_figures)

-- K02: PMUA innovators (all years) by province and the source's own level (1-4); one group has no province.
SELECT 'K02' AS measure_id, 'province_level' AS breakdown, dimension_value AS member, province_code,
       NULL AS region, NULL AS component, replace(metric, 'levels.', '') AS source_level, value, 1 AS divisor
FROM f WHERE source = 'pmua_apptech' AND dataset = 'innovators_all' AND metric LIKE 'levels.%'

-- K09: local employment (people per month) by region.
UNION ALL
SELECT 'K09', 'components', dimension_value, NULL, dimension_value, metric, NULL, value, 1
FROM f WHERE dataset = 'learning_dashboard' AND metric = 'localEmployeeAmount'

-- K10: money paid to local workers and local resource suppliers (THB per month) by region.
UNION ALL
SELECT 'K10', 'components', dimension_value, NULL, dimension_value, metric, NULL, value, 1000000
FROM f WHERE dataset = 'learning_dashboard' AND metric IN ('localEmployeeExpense', 'localResourceExpense')

-- C10: the alternative reading behind the old income figure: local resource spending plus the separately
-- reported excluded resource amount.
UNION ALL
SELECT 'C10_ALTERNATIVE', 'components', coalesce(dimension_value, metric), NULL, dimension_value, metric, NULL, value, 1000000
FROM f WHERE dataset = 'learning_dashboard' AND metric IN ('localResourceExpense', 'excludedResourceExpense')

-- C08: businesses on the Learning dashboard, in four independent breakdowns that each add up to the total.
UNION ALL
SELECT 'C08_REPORTED_BUSINESSES',
       CASE metric WHEN 'businesses_by_category' THEN 'categories' WHEN 'businesses_by_entity_type' THEN 'entityTypes'
                   WHEN 'businesses_by_region' THEN 'geography' ELSE 'provinces' END,
       dimension_value, province_code, CASE WHEN metric = 'businesses_by_region' THEN dimension_value END, NULL, NULL,
       value, 1
FROM f WHERE dataset = 'learning_dashboard' AND metric LIKE 'businesses_by_%';
