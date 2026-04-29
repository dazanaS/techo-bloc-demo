-- ============================================================
-- Governance: column masking (PII) + row-level security (territory)
-- Demonstrates the Unity-Catalog-native governance Vinod & Matt asked about.
-- ============================================================

-- Create the governance groups (idempotent — admin scope on this workspace)
-- We'll fall back to current_user() checks since group bootstrap requires SCIM.

-- ------------------------------------------------------------
-- Masking UDF: email — show full to HR/finance, redact to others
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION dazana_classic_ws_catalog.techo_bloc_governance.mask_email(v STRING)
RETURNS STRING
COMMENT 'Mask email for non-HR/non-finance users: only domain is exposed'
RETURN
  CASE
    WHEN is_account_group_member('techo_hr')      THEN v
    WHEN is_account_group_member('techo_finance') THEN v
    WHEN is_account_group_member('admins')        THEN v
    WHEN v IS NULL                                THEN NULL
    ELSE concat('***@', split(v, '@')[1])
  END;

-- ------------------------------------------------------------
-- Masking UDF: phone — last 4 digits only for non-privileged
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION dazana_classic_ws_catalog.techo_bloc_governance.mask_phone(v STRING)
RETURNS STRING
COMMENT 'Mask phone to last 4 digits for non-HR/non-sales-leader users'
RETURN
  CASE
    WHEN is_account_group_member('techo_hr')           THEN v
    WHEN is_account_group_member('techo_sales_leader') THEN v
    WHEN is_account_group_member('admins')             THEN v
    WHEN v IS NULL                                     THEN NULL
    ELSE concat('***-***-', right(v, 4))
  END;

-- ------------------------------------------------------------
-- Masking UDF: address — city kept, street redacted
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION dazana_classic_ws_catalog.techo_bloc_governance.mask_address(v STRING)
RETURNS STRING
COMMENT 'Redact street address for non-HR/non-finance users'
RETURN
  CASE
    WHEN is_account_group_member('techo_hr')      THEN v
    WHEN is_account_group_member('techo_finance') THEN v
    WHEN is_account_group_member('admins')        THEN v
    WHEN v IS NULL                                THEN NULL
    ELSE '[REDACTED]'
  END;

-- ------------------------------------------------------------
-- Masking UDF: SSN — completely hidden except for HR
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION dazana_classic_ws_catalog.techo_bloc_governance.mask_ssn(v STRING)
RETURNS STRING
COMMENT 'SSN: visible only to techo_hr group; everyone else gets a redacted token'
RETURN
  CASE
    WHEN is_account_group_member('techo_hr') THEN v
    WHEN is_account_group_member('admins')   THEN v
    WHEN v IS NULL                           THEN NULL
    ELSE 'XXX-XX-XXXX'
  END;

-- ------------------------------------------------------------
-- Masking UDF: salary — visible only to HR/finance
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION dazana_classic_ws_catalog.techo_bloc_governance.mask_salary(v DOUBLE)
RETURNS DOUBLE
COMMENT 'Annual salary: visible only to HR/finance; otherwise NULL'
RETURN
  CASE
    WHEN is_account_group_member('techo_hr')      THEN v
    WHEN is_account_group_member('techo_finance') THEN v
    WHEN is_account_group_member('admins')        THEN v
    ELSE NULL
  END;

-- ------------------------------------------------------------
-- Row-filter UDF: territory — filter to user's assigned territory
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION dazana_classic_ws_catalog.techo_bloc_governance.row_filter_territory(territory STRING)
RETURNS BOOLEAN
COMMENT 'RLS: regional managers only see their own territory; leaders/admins see all'
RETURN
  CASE
    WHEN is_account_group_member('techo_global_leadership') THEN true
    WHEN is_account_group_member('admins')                  THEN true
    WHEN is_account_group_member('techo_us_east')      AND territory = 'US-East'      THEN true
    WHEN is_account_group_member('techo_us_west')      AND territory = 'US-West'      THEN true
    WHEN is_account_group_member('techo_canada_east') AND territory = 'Canada-East'   THEN true
    WHEN is_account_group_member('techo_canada_west') AND territory = 'Canada-West'   THEN true
    ELSE false
  END;

-- ============================================================
-- Apply column masks to silver dim_customer (and the gold view inherits via lineage)
-- ============================================================
ALTER TABLE dazana_classic_ws_catalog.techo_bloc_silver.dim_customer
  ALTER COLUMN email          SET MASK dazana_classic_ws_catalog.techo_bloc_governance.mask_email;
ALTER TABLE dazana_classic_ws_catalog.techo_bloc_silver.dim_customer
  ALTER COLUMN phone          SET MASK dazana_classic_ws_catalog.techo_bloc_governance.mask_phone;
ALTER TABLE dazana_classic_ws_catalog.techo_bloc_silver.dim_customer
  ALTER COLUMN address_line1  SET MASK dazana_classic_ws_catalog.techo_bloc_governance.mask_address;

-- Apply column masks to silver dim_employee
ALTER TABLE dazana_classic_ws_catalog.techo_bloc_silver.dim_employee
  ALTER COLUMN ssn                SET MASK dazana_classic_ws_catalog.techo_bloc_governance.mask_ssn;
ALTER TABLE dazana_classic_ws_catalog.techo_bloc_silver.dim_employee
  ALTER COLUMN annual_salary_usd  SET MASK dazana_classic_ws_catalog.techo_bloc_governance.mask_salary;

-- ============================================================
-- Apply RLS by territory on the silver dim_customer and the GL fact
-- ============================================================
ALTER TABLE dazana_classic_ws_catalog.techo_bloc_silver.dim_customer
  SET ROW FILTER dazana_classic_ws_catalog.techo_bloc_governance.row_filter_territory ON (territory);

ALTER TABLE dazana_classic_ws_catalog.techo_bloc_silver.fact_gl_transactions
  SET ROW FILTER dazana_classic_ws_catalog.techo_bloc_governance.row_filter_territory ON (territory);
