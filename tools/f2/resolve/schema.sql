-- Tables written by the Resolve stage (rebuilt on every run).

CREATE OR REPLACE TABLE entity_members (
    entity      VARCHAR NOT NULL,  -- innovation | operator | offering | offering_family | person | cultural_record | activity
    entity_id   VARCHAR NOT NULL,
    source      VARCHAR NOT NULL,
    record_id   VARCHAR NOT NULL,
    PRIMARY KEY (entity, source, record_id)
);

-- Every candidate pair a rule or a decision looked at.
CREATE OR REPLACE TABLE match_pairs (
    entity        VARCHAR NOT NULL,
    a_source      VARCHAR NOT NULL,
    a_record_id   VARCHAR NOT NULL,
    b_source      VARCHAR NOT NULL,
    b_record_id   VARCHAR NOT NULL,
    rule          VARCHAR,           -- the rule that looked at the pair (NULL: only a decision did)
    rule_outcome  VARCHAR,           -- same | different | queue
    status        VARCHAR NOT NULL,  -- same | different | queue (waits for a decision) | blocked (rule said same,
                                     --   but a decision keeps the two entities apart)
    basis         VARCHAR NOT NULL,  -- decision:<ref> | rule:<name> | judge, "+transitive" when it follows from other pairs
    judge         VARCHAR            -- the LLM judge's answer, decision/confidence (a proposal unless basis = judge)
);

-- Decisions that no longer fit the data: records gone, or two decisions that contradict each other.
CREATE OR REPLACE TABLE decision_issues (
    entity        VARCHAR NOT NULL,
    decision_ref  VARCHAR NOT NULL,
    issue         VARCHAR NOT NULL,
    detail        JSON
);
