-- ============================================================
-- Bronze: AX 2012 (legacy 2018-2024) + UKG/HubSpot/GA
-- ============================================================

-- ------------------------------------------------------------
-- AX 2012 CustInvoiceJour (invoice headers, legacy)
-- ------------------------------------------------------------
CREATE OR REPLACE TABLE ax2012_custinvoicejour
COMMENT 'Legacy AX 2012 CustInvoiceJour: invoice headers from on-prem SQL Server (2019-2024)'
TBLPROPERTIES (source_system='AX_2012', source_path='dbo.CUSTINVOICEJOUR', is_legacy='true')
AS
SELECT
  CONCAT('INV-A-', LPAD(CAST(id AS STRING), 7, '0'))                              AS INVOICEID,
  CONCAT('CUST', LPAD(CAST((id*7 % 4800) + 1 AS STRING), 6, '0'))                  AS INVOICEACCOUNT,
  date_add(DATE'2019-01-01', CAST(id*7 % 1825 AS INT))                             AS INVOICEDATE,
  ROUND(50 + (CAST(abs(hash(id)) % 12000000 AS DOUBLE) / 1000.0), 2)               AS INVOICEAMOUNT,
  ROUND(0  + (CAST(abs(hash(id+11)) % 1500000 AS DOUBLE) / 1000.0), 2)             AS SALESTAXAMOUNT,
  'USD'                                                                            AS CURRENCYCODE,
  CASE WHEN id % 23 = 0 THEN 1 ELSE 0 END                                          AS POSTED,
  'tcb'                                                                            AS DATAAREAID
FROM range(28000) AS t(id);

-- ------------------------------------------------------------
-- AX 2012 GL Transactions (LedgerJournalTrans)
-- 5 years of GL — this is the "more than 2 years GL" data Techo-Bloc cannot fit
-- in their 1GB Power BI Pro semantic model
-- ------------------------------------------------------------
CREATE OR REPLACE TABLE ax2012_gl_transactions
COMMENT 'Legacy AX 2012 LedgerJournalTrans: 5+ years of GL — primary driver for SQL Warehouse migration (1GB Power BI cap)'
TBLPROPERTIES (source_system='AX_2012', source_path='dbo.LEDGERJOURNALTRANS', is_legacy='true')
AS
WITH accounts AS (
  SELECT * FROM VALUES
    ('4010','Sales Revenue - Pavers',          'REVENUE'),
    ('4020','Sales Revenue - Slabs',           'REVENUE'),
    ('4030','Sales Revenue - Walls',           'REVENUE'),
    ('4040','Sales Revenue - FirePits',        'REVENUE'),
    ('4101','Discounts Allowed',               'REVENUE_CONTRA'),
    ('5010','COGS - Raw Materials',            'COGS'),
    ('5020','COGS - Direct Labor',             'COGS'),
    ('5030','COGS - Manufacturing Overhead',   'COGS'),
    ('5210','Freight Out',                     'OPEX'),
    ('5220','Marketing & Trade Shows',         'OPEX'),
    ('6010','Salaries & Benefits',             'OPEX'),
    ('6020','Rent & Utilities',                'OPEX'),
    ('6030','IT & Software (Power BI, ERP)',   'OPEX'),
    ('7010','Capex - Equipment',               'CAPEX')
  AS t(GL_ACCOUNT, GL_DESCRIPTION, GL_CATEGORY)
)
SELECT
  CONCAT('VCH-', LPAD(CAST(id AS STRING), 8, '0'))                                 AS VOUCHER,
  date_add(DATE'2019-01-01', CAST(id*3 % 2190 AS INT))                             AS TRANSDATE,
  a.GL_ACCOUNT                                                                     AS ACCOUNTNUM,
  a.GL_DESCRIPTION                                                                 AS GL_DESCRIPTION,
  a.GL_CATEGORY                                                                    AS GL_CATEGORY,
  CASE WHEN a.GL_CATEGORY = 'REVENUE'        THEN -ROUND(500 + (CAST(abs(hash(id))    % 50000000 AS DOUBLE)/1000.0), 2)
       WHEN a.GL_CATEGORY = 'REVENUE_CONTRA' THEN  ROUND(10  + (CAST(abs(hash(id+1))  %   500000 AS DOUBLE)/1000.0), 2)
       WHEN a.GL_CATEGORY = 'COGS'           THEN  ROUND(200 + (CAST(abs(hash(id+2))  % 25000000 AS DOUBLE)/1000.0), 2)
       WHEN a.GL_CATEGORY = 'OPEX'           THEN  ROUND(100 + (CAST(abs(hash(id+3))  %  8000000 AS DOUBLE)/1000.0), 2)
       ELSE                                        ROUND(5000+ (CAST(abs(hash(id+4))  % 95000000 AS DOUBLE)/1000.0), 2) END
                                                                                   AS AMOUNTMST,
  'USD'                                                                            AS CURRENCYCODE,
  CASE WHEN id % 18 < 8  THEN 'BU-RES'
       WHEN id % 18 < 14 THEN 'BU-PRO' ELSE 'BU-COM' END                           AS DIM_BUSINESS_UNIT,
  CASE WHEN id % 4 = 0 THEN 'US-East'
       WHEN id % 4 = 1 THEN 'US-West'
       WHEN id % 4 = 2 THEN 'Canada-East' ELSE 'Canada-West' END                   AS DIM_TERRITORY,
  'tcb'                                                                            AS DATAAREAID
FROM (SELECT id, MOD(id, 14) AS ai FROM range(600000)) r
JOIN accounts a ON r.ai = (length(a.GL_ACCOUNT) % 14);

-- ------------------------------------------------------------
-- UKG (HR) — employees with PII (SSN, salary)
-- ------------------------------------------------------------
CREATE OR REPLACE TABLE ukg_employees
COMMENT 'UKG HR feed: employee master with PII (SSN, salary) — masked in silver/gold for non-HR users'
TBLPROPERTIES (source_system='UKG', source_path='/api/v2/employees', contains_pii='true')
AS
WITH first_names AS (
  SELECT * FROM VALUES ('Marie'),('Jean'),('Sophie'),('Luc'),('Pierre'),('Emily'),('Michael'),('Sarah'),('David'),('Jessica')
  AS t(fn)
),
last_names AS (
  SELECT * FROM VALUES ('Lavoie'),('Pelletier'),('Cote'),('Beaulieu'),('Anderson'),('Thompson'),('Martinez'),('Lopez'),('Lee'),('Patel')
  AS t(ln)
),
depts AS (
  SELECT * FROM VALUES
    ('SALES',   'Sales',         70000),
    ('OPS',     'Operations',    65000),
    ('FIN',     'Finance',       80000),
    ('IT',      'Information Technology', 95000),
    ('MFG',     'Manufacturing', 55000),
    ('MKTG',    'Marketing',     78000)
  AS t(dept_code, dept_name, base_salary)
)
SELECT
  CONCAT('EMP', LPAD(CAST(r.id AS STRING), 5, '0'))                                AS EMPLOYEE_ID,
  CONCAT(fn.fn, ' ', ln.ln)                                                        AS FULL_NAME,
  -- Synthetic SSN (NOT real)
  CONCAT(LPAD(CAST(100 + (r.id*13 % 800) AS STRING),3,'0'), '-',
         LPAD(CAST(10  + (r.id*7  % 80)  AS STRING),2,'0'), '-',
         LPAD(CAST(1000+ (r.id*31 % 9000) AS STRING),4,'0'))                       AS SSN,
  date_add(DATE'2014-01-01', CAST(r.id*5 % 4380 AS INT))                           AS HIRE_DATE,
  ROUND(d.base_salary + (CAST(abs(hash(r.id)) % 60000 AS DOUBLE)), 2)              AS ANNUAL_SALARY,
  d.dept_code                                                                      AS DEPARTMENT_CODE,
  d.dept_name                                                                      AS DEPARTMENT,
  LOWER(CONCAT(fn.fn, '.', ln.ln, '@techo-bloc.example.com'))                      AS WORK_EMAIL,
  CASE WHEN r.id % 4 = 0 THEN 'US-East'
       WHEN r.id % 4 = 1 THEN 'US-West'
       WHEN r.id % 4 = 2 THEN 'Canada-East' ELSE 'Canada-West' END                 AS TERRITORY,
  CASE WHEN r.id % 31 = 0 THEN 'TERMINATED' ELSE 'ACTIVE' END                      AS STATUS
FROM (SELECT id, MOD(id, 10) AS fi, MOD(id, 10) AS li, MOD(id, 6) AS di FROM range(540)) r
JOIN first_names fn ON r.fi = (length(fn.fn) % 10)
JOIN last_names  ln ON r.li = (length(ln.ln) % 10)
JOIN depts       d  ON r.di = (length(d.dept_code) % 6);

-- ------------------------------------------------------------
-- HubSpot deals (CRM)
-- ------------------------------------------------------------
CREATE OR REPLACE TABLE hubspot_deals
COMMENT 'HubSpot CRM deals — pulled via Databricks Jobs/REST API (per Vinod)'
TBLPROPERTIES (source_system='HubSpot', source_path='/crm/v3/objects/deals')
AS
SELECT
  CONCAT('HS-', LPAD(CAST(id AS STRING),7,'0'))                                    AS DEAL_ID,
  CONCAT('Deal — Project ', CAST(id AS STRING))                                    AS DEAL_NAME,
  ROUND(2000 + (CAST(abs(hash(id)) % 250000000 AS DOUBLE) / 1000.0), 2)            AS AMOUNT_USD,
  element_at(array('appointmentscheduled','qualifiedtobuy','presentationscheduled','decisionmakerboughtin','contractsent','closedwon','closedlost'),
             1 + CAST(id % 7 AS INT))                                              AS DEALSTAGE,
  CONCAT('CUST', LPAD(CAST(((id*11) % 4800) + 1 AS STRING), 6, '0'))               AS ASSOCIATED_ACCOUNTNUM,
  date_add(DATE'2024-01-01', CAST(id*5 % 730 AS INT))                              AS CREATED_AT,
  CASE WHEN id % 4 = 0 THEN 'US-East'
       WHEN id % 4 = 1 THEN 'US-West'
       WHEN id % 4 = 2 THEN 'Canada-East' ELSE 'Canada-West' END                    AS TERRITORY,
  element_at(array('Trade Show','Web Form','Referral','Cold Call','Pro Loyalty Program','Dealer Referral'),
             1 + CAST(id % 6 AS INT))                                              AS LEAD_SOURCE
FROM range(8500) AS t(id);

-- ------------------------------------------------------------
-- Google Analytics sessions
-- ------------------------------------------------------------
CREATE OR REPLACE TABLE ga_sessions
COMMENT 'Google Analytics sessions — pulled via Databricks Jobs/REST API'
TBLPROPERTIES (source_system='GoogleAnalytics', source_path='/analyticsdata/v1beta/runReport')
AS
SELECT
  CONCAT('SES-', LPAD(CAST(id AS STRING), 9, '0'))                                 AS SESSION_ID,
  CONCAT('U-', LPAD(CAST((id*17) % 50000 AS STRING), 6, '0'))                      AS USER_PSEUDO_ID,
  date_add(DATE'2024-06-01', CAST(id*2 % 700 AS INT))                              AS SESSION_DATE,
  element_at(array('google','direct','facebook','instagram','pinterest','houzz','referral','email'),
             1 + CAST(id % 8 AS INT))                                              AS SOURCE,
  element_at(array('organic','cpc','social','referral','email','none'),
             1 + CAST(id % 6 AS INT))                                              AS MEDIUM,
  element_at(array('Spring2026-Pavers','HouzzAlwaysOn','ProgramLaunch-Steps','Brand','none','Trade-Hardscape-Show'),
             1 + CAST(id % 6 AS INT))                                              AS CAMPAIGN,
  element_at(array('mobile','desktop','tablet'),  1 + CAST(id % 3 AS INT))         AS DEVICE_CATEGORY,
  CASE WHEN id % 4 = 0 THEN 'United States'
       WHEN id % 4 = 1 THEN 'United States'
       WHEN id % 4 = 2 THEN 'Canada' ELSE 'Canada' END                             AS COUNTRY,
  element_at(array('US-East','US-West','Canada-East','Canada-West'), 1 + CAST(id % 4 AS INT))
                                                                                   AS TERRITORY,
  CONCAT('ITM', LPAD(CAST(((id*7)%240)+1 AS STRING), 5, '0'))                       AS PRODUCT_VIEWED,
  element_at(array('page_view','add_to_inspiration','contact_form','find_dealer','request_quote'),
             1 + CAST(id % 5 AS INT))                                              AS EVENT_NAME
FROM range(150000) AS t(id);
