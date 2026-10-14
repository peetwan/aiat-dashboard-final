-- Entity tables written by the Clean stage. One row per thing a source states.
-- (source, record_id) is the key everything else (decisions, matching) refers to.
-- Place columns are official codes from tools/f2/geo.py; NULL = not stated or not resolvable.
-- kind (operators, offerings, people, activities):
--   listed    = the source lists it (a seller, product, profile, ...)
--   declared  = a source directory row declares it
--   extracted = a reviewer (or later an LLM) found it in a record's text
--               (data/runtime/f2/decisions/extractions.json); record_id is "<source record id>#<name>",
--               review_status says whether it counts.

CREATE TABLE runs (
    source      VARCHAR PRIMARY KEY,
    raw_folder  VARCHAR NOT NULL,   -- data/runtime/f2/raw/<raw_folder>/<run_id>
    run_id      VARCHAR NOT NULL
);

-- Innovations ---------------------------------------------------------------

CREATE TABLE innovations (
    source       VARCHAR NOT NULL,  -- apptech_mru | rinmp | pmua_apptech | icommunity
    record_id    VARCHAR NOT NULL,  -- one listing; iCommunity lists one innovation under several groups
    upstream_id  VARCHAR NOT NULL,  -- the source's own innovation id (shared by repeated listings)
    title        VARCHAR,
    description  VARCHAR,           -- all description sections, "label: text" per line
    category     VARCHAR,
    institution  VARCHAR,
    ip_number    VARCHAR,           -- a stated patent / request number (must contain a digit)
    url          VARCHAR,
    raw_ref      VARCHAR NOT NULL,  -- file#path of the raw record
    details      JSON,              -- other source-specific fields, kept for review pages
    PRIMARY KEY (source, record_id)
);

CREATE TABLE innovation_readiness (
    source       VARCHAR NOT NULL,
    record_id    VARCHAR NOT NULL,
    scale        VARCHAR NOT NULL,  -- TRL | SRL | ATL
    level        INTEGER,           -- NULL when the stated value is not a valid level
    start_level  INTEGER,           -- iCommunity states start and end of the project
    raw          VARCHAR,
    stated_in    VARCHAR NOT NULL   -- which part of the source states it (detail, map, export, ...)
);

CREATE TABLE innovation_places (
    source           VARCHAR NOT NULL,
    record_id        VARCHAR NOT NULL,
    role             VARCHAR NOT NULL,  -- use (where it is used) | profile (where the record says it is)
    stated_in        VARCHAR NOT NULL,  -- address, text, map, location, ...
    province_code    VARCHAR,
    district_code    VARCHAR,
    subdistrict_code VARCHAR,
    province         VARCHAR,
    district         VARCHAR,
    subdistrict      VARCHAR,
    geo_note         VARCHAR,           -- how the written name was fixed (see geo.py)
    raw              VARCHAR            -- the place as written
);

-- People ----------------------------------------------------------------------
-- One row per person per record they appear in. Same-person matching is the Resolve stage's job.

CREATE TABLE people (
    source           VARCHAR NOT NULL,
    record_id        VARCHAR NOT NULL,  -- the person's own record id, or "<about record>#<role>#<name key>" (text.member_id)
    kind             VARCHAR NOT NULL,
    review_status    VARCHAR,
    role             VARCHAR NOT NULL,  -- community_innovator, researcher, lead, co, inventor, owner, ...
    title            VARCHAR,           -- raw title(s) as written: นาย, นางสาว, รศ.ดร. ...
    name             VARCHAR NOT NULL,  -- name without title
    sex              VARCHAR,           -- male | female, only when the title states it
    institution      VARCHAR,
    faculty          VARCHAR,
    person_ref       VARCHAR,           -- the source's own person / account id, when it has one
    about_kind       VARCHAR,           -- what the record is about: innovation | person | cultural_record | ...
    about_record_id  VARCHAR,           -- record_id in that table (same source)
    province_code    VARCHAR,
    district_code    VARCHAR,
    subdistrict_code VARCHAR,
    province         VARCHAR,
    district         VARCHAR,
    subdistrict      VARCHAR,
    geo_note         VARCHAR,
    raw_ref          VARCHAR NOT NULL,
    details          JSON,
    PRIMARY KEY (source, record_id)
);

-- Development scores a source states for a person (iCommunity community innovators).
CREATE TABLE assessments (
    source            VARCHAR NOT NULL,
    person_record_id  VARCHAR NOT NULL,  -- people.record_id
    dimension         VARCHAR NOT NULL,
    start_level       INTEGER,
    current_level     INTEGER,
    raw_ref           VARCHAR NOT NULL
);

-- Businesses (K05 operators) and what they offer (K07 offerings) -------------

CREATE TABLE operators (
    source           VARCHAR NOT NULL,
    record_id        VARCHAR NOT NULL,
    kind             VARCHAR NOT NULL,
    review_status    VARCHAR,
    name             VARCHAR NOT NULL,
    name_quality     VARCHAR NOT NULL,  -- named | code (no usable name, e.g. "04_97", "อาหาร 04_34")
    description      VARCHAR,
    province_code    VARCHAR,
    district_code    VARCHAR,
    subdistrict_code VARCHAR,
    province         VARCHAR,
    district         VARCHAR,
    subdistrict      VARCHAR,
    geo_note         VARCHAR,
    address_raw      VARCHAR,
    raw_ref          VARCHAR NOT NULL,
    details          JSON,
    PRIMARY KEY (source, record_id)
);

CREATE TABLE offerings (
    source              VARCHAR NOT NULL,
    record_id           VARCHAR NOT NULL,
    kind                VARCHAR NOT NULL,
    review_status       VARCHAR,
    name                VARCHAR NOT NULL,
    description         VARCHAR,
    category            VARCHAR,
    price_thb           DOUBLE,
    province_code       VARCHAR,
    district_code       VARCHAR,
    subdistrict_code    VARCHAR,
    province            VARCHAR,
    district            VARCHAR,
    subdistrict         VARCHAR,
    geo_note            VARCHAR,
    url                 VARCHAR,
    raw_ref             VARCHAR NOT NULL,
    details             JSON,
    PRIMARY KEY (source, record_id)
);

-- Which operator sells / makes which offering (same source). An offering can have several.
CREATE TABLE offering_operators (
    source              VARCHAR NOT NULL,
    offering_record_id  VARCHAR NOT NULL,
    operator_record_id  VARCHAR NOT NULL,
    relationship        VARCHAR NOT NULL,  -- seller | manufacturer_of | ...
    basis               VARCHAR NOT NULL   -- how the link is known
);

-- Cultural records: Cultural Map subjects (CD-…) and AtLocal programme areas ----

CREATE TABLE cultural_records (
    source           VARCHAR NOT NULL,
    record_id        VARCHAR NOT NULL,
    title            VARCHAR NOT NULL,
    title_en         VARCHAR,
    category         VARCHAR,           -- Cultural Map primary category code (CS = cultural space); AtLocal: area
    cultural_type    VARCHAR,           -- T (tangible) | I (intangible) ...
    categories       JSON,              -- additional category codes
    description      VARCHAR,
    province_code    VARCHAR,
    district_code    VARCHAR,
    subdistrict_code VARCHAR,
    province         VARCHAR,
    district         VARCHAR,
    subdistrict      VARCHAR,
    geo_note         VARCHAR,
    latitude         DOUBLE,
    longitude        DOUBLE,
    url              VARCHAR,
    raw_ref          VARCHAR NOT NULL,
    details          JSON,
    PRIMARY KEY (source, record_id)
);

-- Publications (posts, articles, festival / activity pages) and the activities they report --------

CREATE TABLE publications (
    source        VARCHAR NOT NULL,
    record_id     VARCHAR NOT NULL,
    kind          VARCHAR NOT NULL,  -- the source's page type: activity_post, festival, culture, article, ...
    title         VARCHAR,
    text          VARCHAR,
    published_at  VARCHAR,
    url           VARCHAR,
    raw_ref       VARCHAR NOT NULL,
    details       JSON,
    PRIMARY KEY (source, record_id)
);

CREATE TABLE activities (
    source                VARCHAR NOT NULL,
    record_id             VARCHAR NOT NULL,
    kind                  VARCHAR NOT NULL,
    review_status         VARCHAR,
    name                  VARCHAR NOT NULL,
    publication_record_id VARCHAR,          -- publications.record_id it was found in
    start_date            DATE,
    end_date              DATE,
    venues                JSON,             -- [{province_code, role}]; role "online_delivery" = no physical venue
    raw_ref               VARCHAR NOT NULL,
    details               JSON,
    PRIMARY KEY (source, record_id)
);

-- Numbers a source publishes as totals (dashboards), kept as stated -----------

CREATE TABLE reported_figures (
    source           VARCHAR NOT NULL,
    dataset          VARCHAR NOT NULL,  -- which dashboard / file
    metric           VARCHAR NOT NULL,
    dimension        VARCHAR,           -- province | region | category | level | ... (NULL = headline)
    dimension_value  VARCHAR,
    province_code    VARCHAR,
    value            DOUBLE,
    raw_ref          VARCHAR NOT NULL
);
