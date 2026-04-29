-- Refresh governance UDFs to also accept workspace admins (is_member('admins'))
-- so the demo can be run by Dazana / SAs without account-group provisioning.

CREATE OR REPLACE FUNCTION dazana_classic_ws_catalog.techo_bloc_governance.mask_email(v STRING)
RETURNS STRING
COMMENT 'Mask email except for HR/Finance/admins'
RETURN
  CASE
    WHEN is_member('admins')                      THEN v
    WHEN is_account_group_member('techo_hr')      THEN v
    WHEN is_account_group_member('techo_finance') THEN v
    WHEN v IS NULL                                THEN NULL
    ELSE concat('***@', split(v, '@')[1])
  END;

CREATE OR REPLACE FUNCTION dazana_classic_ws_catalog.techo_bloc_governance.mask_phone(v STRING)
RETURNS STRING
COMMENT 'Mask phone to last 4 except for HR/Sales-Leader/admins'
RETURN
  CASE
    WHEN is_member('admins')                            THEN v
    WHEN is_account_group_member('techo_hr')            THEN v
    WHEN is_account_group_member('techo_sales_leader')  THEN v
    WHEN v IS NULL                                      THEN NULL
    ELSE concat('***-***-', right(v, 4))
  END;

CREATE OR REPLACE FUNCTION dazana_classic_ws_catalog.techo_bloc_governance.mask_address(v STRING)
RETURNS STRING
COMMENT 'Redact street address except for HR/Finance/admins'
RETURN
  CASE
    WHEN is_member('admins')                      THEN v
    WHEN is_account_group_member('techo_hr')      THEN v
    WHEN is_account_group_member('techo_finance') THEN v
    WHEN v IS NULL                                THEN NULL
    ELSE '[REDACTED]'
  END;

CREATE OR REPLACE FUNCTION dazana_classic_ws_catalog.techo_bloc_governance.mask_ssn(v STRING)
RETURNS STRING
COMMENT 'SSN visible only to HR or admins'
RETURN
  CASE
    WHEN is_member('admins')                  THEN v
    WHEN is_account_group_member('techo_hr')  THEN v
    WHEN v IS NULL                            THEN NULL
    ELSE 'XXX-XX-XXXX'
  END;

CREATE OR REPLACE FUNCTION dazana_classic_ws_catalog.techo_bloc_governance.mask_salary(v DOUBLE)
RETURNS DOUBLE
COMMENT 'Annual salary visible only to HR/Finance/admins'
RETURN
  CASE
    WHEN is_member('admins')                      THEN v
    WHEN is_account_group_member('techo_hr')      THEN v
    WHEN is_account_group_member('techo_finance') THEN v
    ELSE NULL
  END;

CREATE OR REPLACE FUNCTION dazana_classic_ws_catalog.techo_bloc_governance.row_filter_territory(territory STRING)
RETURNS BOOLEAN
COMMENT 'RLS: regional managers see only their territory; leaders/admins see all'
RETURN
  CASE
    WHEN is_member('admins')                                                      THEN true
    WHEN is_account_group_member('techo_global_leadership')                       THEN true
    WHEN is_account_group_member('techo_us_east')      AND territory = 'US-East'  THEN true
    WHEN is_account_group_member('techo_us_west')      AND territory = 'US-West'  THEN true
    WHEN is_account_group_member('techo_canada_east') AND territory = 'Canada-East' THEN true
    WHEN is_account_group_member('techo_canada_west') AND territory = 'Canada-West' THEN true
    ELSE false
  END;
