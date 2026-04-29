-- ============================================================
-- Demo persona override: lets us flip between HR / Finance / Sales Rep /
-- Regional Manager / Leader during the live demo by updating one row.
-- In production, replace the persona lookup with real account groups
-- (is_account_group_member calls are still preserved as fallbacks).
-- ============================================================

CREATE TABLE IF NOT EXISTS dazana_classic_ws_catalog.techo_bloc_governance.demo_persona (
  user_email   STRING NOT NULL,
  persona      STRING NOT NULL  COMMENT 'One of: HR, FINANCE, SALES_LEADER, SALES_REP, REGIONAL_MGR_US_EAST, REGIONAL_MGR_US_WEST, REGIONAL_MGR_CA_EAST, REGIONAL_MGR_CA_WEST, GLOBAL_LEADERSHIP',
  set_at       TIMESTAMP
);

-- Default Dazana to GLOBAL_LEADERSHIP so the dashboard renders fully on first open
DELETE FROM dazana_classic_ws_catalog.techo_bloc_governance.demo_persona
  WHERE user_email = 'dazana.hasan@databricks.com';
INSERT INTO dazana_classic_ws_catalog.techo_bloc_governance.demo_persona (user_email, persona, set_at)
VALUES ('dazana.hasan@databricks.com', 'GLOBAL_LEADERSHIP', current_timestamp());

-- Helper: read the active persona for the calling user
CREATE OR REPLACE FUNCTION dazana_classic_ws_catalog.techo_bloc_governance.active_persona()
RETURNS STRING
COMMENT 'Returns the persona configured for the current_user() (used in masking and RLS UDFs for the demo).'
RETURN (
  SELECT persona
  FROM dazana_classic_ws_catalog.techo_bloc_governance.demo_persona
  WHERE user_email = current_user()
  ORDER BY set_at DESC
  LIMIT 1
);

-- Re-define masking UDFs to consider the demo persona first, then fall back to account groups
CREATE OR REPLACE FUNCTION dazana_classic_ws_catalog.techo_bloc_governance.mask_email(v STRING)
RETURNS STRING
RETURN
  CASE
    WHEN dazana_classic_ws_catalog.techo_bloc_governance.active_persona() IN ('HR','FINANCE','GLOBAL_LEADERSHIP') THEN v
    WHEN is_account_group_member('techo_hr')      THEN v
    WHEN is_account_group_member('techo_finance') THEN v
    WHEN v IS NULL                                THEN NULL
    ELSE concat('***@', split(v,'@')[1])
  END;

CREATE OR REPLACE FUNCTION dazana_classic_ws_catalog.techo_bloc_governance.mask_phone(v STRING)
RETURNS STRING
RETURN
  CASE
    WHEN dazana_classic_ws_catalog.techo_bloc_governance.active_persona() IN ('HR','SALES_LEADER','GLOBAL_LEADERSHIP') THEN v
    WHEN is_account_group_member('techo_hr')           THEN v
    WHEN is_account_group_member('techo_sales_leader') THEN v
    WHEN v IS NULL                                     THEN NULL
    ELSE concat('***-***-', right(v,4))
  END;

CREATE OR REPLACE FUNCTION dazana_classic_ws_catalog.techo_bloc_governance.mask_address(v STRING)
RETURNS STRING
RETURN
  CASE
    WHEN dazana_classic_ws_catalog.techo_bloc_governance.active_persona() IN ('HR','FINANCE','GLOBAL_LEADERSHIP') THEN v
    WHEN is_account_group_member('techo_hr')      THEN v
    WHEN is_account_group_member('techo_finance') THEN v
    WHEN v IS NULL                                THEN NULL
    ELSE '[REDACTED]'
  END;

CREATE OR REPLACE FUNCTION dazana_classic_ws_catalog.techo_bloc_governance.mask_ssn(v STRING)
RETURNS STRING
RETURN
  CASE
    WHEN dazana_classic_ws_catalog.techo_bloc_governance.active_persona() = 'HR' THEN v
    WHEN is_account_group_member('techo_hr')                                     THEN v
    WHEN v IS NULL                                                               THEN NULL
    ELSE 'XXX-XX-XXXX'
  END;

CREATE OR REPLACE FUNCTION dazana_classic_ws_catalog.techo_bloc_governance.mask_salary(v DOUBLE)
RETURNS DOUBLE
RETURN
  CASE
    WHEN dazana_classic_ws_catalog.techo_bloc_governance.active_persona() IN ('HR','FINANCE') THEN v
    WHEN is_account_group_member('techo_hr')      THEN v
    WHEN is_account_group_member('techo_finance') THEN v
    ELSE NULL
  END;

CREATE OR REPLACE FUNCTION dazana_classic_ws_catalog.techo_bloc_governance.row_filter_territory(territory STRING)
RETURNS BOOLEAN
RETURN
  CASE
    WHEN dazana_classic_ws_catalog.techo_bloc_governance.active_persona() IN ('GLOBAL_LEADERSHIP','HR','FINANCE','SALES_LEADER') THEN true
    WHEN dazana_classic_ws_catalog.techo_bloc_governance.active_persona() = 'REGIONAL_MGR_US_EAST'  AND territory = 'US-East'      THEN true
    WHEN dazana_classic_ws_catalog.techo_bloc_governance.active_persona() = 'REGIONAL_MGR_US_WEST'  AND territory = 'US-West'      THEN true
    WHEN dazana_classic_ws_catalog.techo_bloc_governance.active_persona() = 'REGIONAL_MGR_CA_EAST' AND territory = 'Canada-East'   THEN true
    WHEN dazana_classic_ws_catalog.techo_bloc_governance.active_persona() = 'REGIONAL_MGR_CA_WEST' AND territory = 'Canada-West'   THEN true
    -- Production fallback: real account groups
    WHEN is_account_group_member('techo_global_leadership') THEN true
    WHEN is_account_group_member('techo_us_east')      AND territory = 'US-East'    THEN true
    WHEN is_account_group_member('techo_us_west')      AND territory = 'US-West'    THEN true
    WHEN is_account_group_member('techo_canada_east') AND territory = 'Canada-East' THEN true
    WHEN is_account_group_member('techo_canada_west') AND territory = 'Canada-West' THEN true
    ELSE false
  END;

-- Helper: switch persona during the demo
-- USAGE: CALL or  UPDATE governance.demo_persona SET persona='SALES_REP' WHERE user_email=current_user();
CREATE OR REPLACE PROCEDURE dazana_classic_ws_catalog.techo_bloc_governance.set_persona(new_persona STRING)
COMMENT 'Live demo helper: change current user persona (HR/FINANCE/SALES_LEADER/SALES_REP/REGIONAL_MGR_US_EAST/REGIONAL_MGR_US_WEST/REGIONAL_MGR_CA_EAST/REGIONAL_MGR_CA_WEST/GLOBAL_LEADERSHIP)'
LANGUAGE SQL
AS BEGIN
  DELETE FROM dazana_classic_ws_catalog.techo_bloc_governance.demo_persona
    WHERE user_email = current_user();
  INSERT INTO dazana_classic_ws_catalog.techo_bloc_governance.demo_persona(user_email, persona, set_at)
    VALUES (current_user(), new_persona, current_timestamp());
END;
