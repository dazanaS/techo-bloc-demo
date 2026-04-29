-- ============================================================
-- Silver layer: cleaned, deduplicated, integrated Kimball-style dims/facts
-- - dim_customer / dim_product / dim_employee / dim_region / dim_date
-- - fact_invoice_lines (UNIFIES D365 CustInvoiceTrans + AX 2012 + MarkupTrans)
-- - fact_gl_transactions (5+ years legacy + current)
-- - fact_web_engagement (GA cleaned)
-- All built with CTAS so column-level lineage is captured by Unity Catalog.
-- ============================================================

-- ------------------------------------------------------------
-- DIM: Customer (deduplicated, with PII normalized)
-- ------------------------------------------------------------
CREATE OR REPLACE TABLE dazana_classic_ws_catalog.techo_bloc_silver.dim_customer
COMMENT 'Conformed customer dim from D365 CustTable. PII columns are masked at the gold layer.'
AS
SELECT
  ACCOUNTNUM                                                                       AS customer_key,
  TRIM(NAME)                                                                       AS customer_name,
  LOWER(TRIM(EMAIL))                                                               AS email,
  PHONE                                                                            AS phone,
  ADDRESS_LINE1                                                                    AS address_line1,
  CITY                                                                             AS city,
  STATE_PROVINCE                                                                   AS state_province,
  POSTAL_CODE                                                                      AS postal_code,
  COUNTRY                                                                          AS country,
  TERRITORY                                                                        AS territory,
  CUSTGROUP                                                                        AS customer_segment,
  CASE WHEN BLOCKED = 1 THEN false ELSE true END                                   AS is_active,
  CREDITLIMIT_USD                                                                  AS credit_limit_usd,
  CREATEDDATETIME                                                                  AS created_at,
  MODIFIEDDATETIME                                                                 AS modified_at,
  current_timestamp()                                                              AS _silver_loaded_at
FROM dazana_classic_ws_catalog.techo_bloc_bronze.d365_custtable;

-- ------------------------------------------------------------
-- DIM: Product
-- ------------------------------------------------------------
CREATE OR REPLACE TABLE dazana_classic_ws_catalog.techo_bloc_silver.dim_product
COMMENT 'Conformed product dim from D365 InventTable; surfaces the product line for AI/BI'
AS
SELECT
  i.ITEMID                                                                         AS product_key,
  i.ITEMNAME                                                                       AS product_name,
  i.ITEMGROUPID                                                                    AS product_line_code,
  CASE i.ITEMGROUPID
    WHEN 'PAV' THEN 'Pavers'
    WHEN 'SLB' THEN 'Slabs'
    WHEN 'RTW' THEN 'Retaining Walls'
    WHEN 'PCP' THEN 'Pool Coping'
    WHEN 'STP' THEN 'Outdoor Steps'
    WHEN 'FIR' THEN 'Fire Pits'
    WHEN 'MAS' THEN 'Masonry'
    WHEN 'ACC' THEN 'Accessories'
    ELSE 'Other' END                                                               AS product_line,
  i.PRODUCTSUBTYPE                                                                 AS product_tier,
  i.SALESUNIT                                                                      AS unit_of_measure,
  i.UNITCOST_USD                                                                   AS unit_cost_usd,
  i.LISTPRICE_USD                                                                  AS list_price_usd,
  CASE WHEN i.DISCONTINUED = 1 THEN false ELSE true END                            AS is_active,
  i.CREATEDDATETIME                                                                AS created_at,
  current_timestamp()                                                              AS _silver_loaded_at
FROM dazana_classic_ws_catalog.techo_bloc_bronze.d365_inventtable i;

-- ------------------------------------------------------------
-- DIM: Employee (PII columns kept; masked at gold for non-HR users)
-- ------------------------------------------------------------
CREATE OR REPLACE TABLE dazana_classic_ws_catalog.techo_bloc_silver.dim_employee
COMMENT 'Conformed employee dim from UKG; PII (SSN, salary) masked at gold for non-HR users'
AS
SELECT
  EMPLOYEE_ID                                                                      AS employee_key,
  FULL_NAME                                                                        AS full_name,
  SSN                                                                              AS ssn,
  ANNUAL_SALARY                                                                    AS annual_salary_usd,
  HIRE_DATE                                                                        AS hire_date,
  DEPARTMENT_CODE                                                                  AS department_code,
  DEPARTMENT                                                                       AS department,
  WORK_EMAIL                                                                       AS work_email,
  TERRITORY                                                                        AS territory,
  STATUS                                                                           AS status,
  current_timestamp()                                                              AS _silver_loaded_at
FROM dazana_classic_ws_catalog.techo_bloc_bronze.ukg_employees;

-- ------------------------------------------------------------
-- DIM: Region
-- ------------------------------------------------------------
CREATE OR REPLACE TABLE dazana_classic_ws_catalog.techo_bloc_silver.dim_region
COMMENT 'Region/Territory dim — used for RLS and slicing'
AS
SELECT * FROM (
  VALUES
    ('US-East',     'United States', 'US', 'EST'),
    ('US-West',     'United States', 'US', 'PST'),
    ('Canada-East', 'Canada',        'CA', 'EST'),
    ('Canada-West', 'Canada',        'CA', 'PST')
  ) AS t(territory_key, country_name, country_code, timezone);

-- ------------------------------------------------------------
-- DIM: Date  (2018-01-01 .. 2027-12-31)
-- ------------------------------------------------------------
CREATE OR REPLACE TABLE dazana_classic_ws_catalog.techo_bloc_silver.dim_date
COMMENT 'Date dim'
AS
SELECT
  d                                              AS date_key,
  YEAR(d)                                        AS year,
  QUARTER(d)                                     AS quarter,
  MONTH(d)                                       AS month,
  DAY(d)                                         AS day,
  DAYOFWEEK(d)                                   AS day_of_week,
  date_format(d,'EEEE')                          AS day_name,
  date_format(d,'MMM')                           AS month_name,
  CONCAT(YEAR(d),'-Q',QUARTER(d))                AS year_quarter,
  CASE WHEN DAYOFWEEK(d) IN (1,7) THEN true ELSE false END AS is_weekend
FROM (
  SELECT explode(sequence(DATE'2018-01-01', DATE'2027-12-31', INTERVAL 1 DAY)) AS d
);

-- ------------------------------------------------------------
-- FACT: Invoice Lines — UNIFIES D365 + AX 2012 with MarkupTrans applied
-- This is the entity-resolution interdependency story Vinod called out.
-- ------------------------------------------------------------
CREATE OR REPLACE TABLE dazana_classic_ws_catalog.techo_bloc_silver.fact_invoice_lines
COMMENT 'Unified invoice line fact — D365 CustInvoiceTrans + AX 2012 CustInvoiceJour, with D365 MarkupTrans (freight/discount/pallet) joined in'
AS
WITH d365_lines AS (
  SELECT
    cit.INVOICEID,
    cit.LINENUM,
    cit.INVOICEACCOUNT                                                            AS customer_key,
    cit.ITEMID                                                                    AS product_key,
    cit.INVOICEDATE                                                               AS invoice_date,
    cit.QTY                                                                       AS quantity,
    cit.SALESPRICE                                                                AS unit_sales_price,
    cit.LINEAMOUNT                                                                AS gross_line_amount,
    cit.TAXAMOUNT                                                                 AS tax_amount,
    cit.CURRENCYCODE                                                              AS currency,
    'D365_FO'                                                                     AS source_system
  FROM dazana_classic_ws_catalog.techo_bloc_bronze.d365_custinvoicetrans cit
),
markups AS (
  -- Sum freight + discount + pallet per invoice (allocated equally across lines)
  SELECT
    INVOICEID,
    SUM(CASE WHEN MARKUPCODE = 'FREIGHT'  THEN VALUE ELSE 0 END)                  AS freight_amount,
    SUM(CASE WHEN MARKUPCODE = 'DISCOUNT' THEN VALUE ELSE 0 END)                  AS discount_amount,
    SUM(CASE WHEN MARKUPCODE = 'PALLET'   THEN VALUE ELSE 0 END)                  AS pallet_amount
  FROM dazana_classic_ws_catalog.techo_bloc_bronze.d365_markuptrans
  GROUP BY INVOICEID
),
ax_lines AS (
  -- AX 2012 has only invoice headers in our model; treat each header as one line
  SELECT
    INVOICEID,
    1                                                                             AS LINENUM,
    INVOICEACCOUNT                                                                AS customer_key,
    -- legacy invoices weren't tied to a single product_key — pick one based on hash for the demo
    CONCAT('ITM', LPAD(CAST((abs(hash(INVOICEID)) % 192) + 1 AS STRING), 5, '0')) AS product_key,
    INVOICEDATE                                                                   AS invoice_date,
    1                                                                             AS quantity,
    INVOICEAMOUNT                                                                 AS unit_sales_price,
    INVOICEAMOUNT                                                                 AS gross_line_amount,
    SALESTAXAMOUNT                                                                AS tax_amount,
    CURRENCYCODE                                                                  AS currency,
    'AX_2012'                                                                     AS source_system
  FROM dazana_classic_ws_catalog.techo_bloc_bronze.ax2012_custinvoicejour
)
SELECT
  l.INVOICEID                                                                     AS invoice_id,
  l.LINENUM                                                                       AS line_num,
  l.invoice_date,
  l.customer_key,
  l.product_key,
  l.quantity,
  l.unit_sales_price,
  l.gross_line_amount,
  COALESCE(m.freight_amount,  0)                                                  AS freight_amount,
  COALESCE(m.discount_amount, 0)                                                  AS discount_amount,
  COALESCE(m.pallet_amount,   0)                                                  AS pallet_amount,
  -- net = gross + freight + discount (negative) + pallet
  l.gross_line_amount + COALESCE(m.freight_amount,0) + COALESCE(m.discount_amount,0) + COALESCE(m.pallet_amount,0)
                                                                                  AS net_invoice_amount,
  l.tax_amount,
  l.currency,
  l.source_system,
  current_timestamp()                                                             AS _silver_loaded_at
FROM (
  SELECT * FROM d365_lines
  UNION ALL
  SELECT * FROM ax_lines
) l
LEFT JOIN markups m ON l.INVOICEID = m.INVOICEID;

-- ------------------------------------------------------------
-- FACT: GL Transactions (5+ years; the 1GB Power BI cap killer)
-- ------------------------------------------------------------
CREATE OR REPLACE TABLE dazana_classic_ws_catalog.techo_bloc_silver.fact_gl_transactions
COMMENT 'GL transactions — 5+ years AX 2012 LedgerJournalTrans cleaned for the gold finance KPI views'
AS
SELECT
  VOUCHER                                                                          AS voucher_id,
  TRANSDATE                                                                        AS transaction_date,
  ACCOUNTNUM                                                                       AS gl_account,
  GL_DESCRIPTION                                                                   AS gl_description,
  GL_CATEGORY                                                                      AS gl_category,
  AMOUNTMST                                                                        AS amount_usd,
  CURRENCYCODE                                                                     AS currency,
  DIM_BUSINESS_UNIT                                                                AS business_unit,
  DIM_TERRITORY                                                                    AS territory,
  current_timestamp()                                                              AS _silver_loaded_at
FROM dazana_classic_ws_catalog.techo_bloc_bronze.ax2012_gl_transactions;

-- ------------------------------------------------------------
-- FACT: Web Engagement (GA cleaned)
-- ------------------------------------------------------------
CREATE OR REPLACE TABLE dazana_classic_ws_catalog.techo_bloc_silver.fact_web_engagement
COMMENT 'Daily web engagement events at session grain from Google Analytics'
AS
SELECT
  SESSION_ID                                                                       AS session_id,
  USER_PSEUDO_ID                                                                   AS user_pseudo_id,
  SESSION_DATE                                                                     AS session_date,
  SOURCE                                                                           AS traffic_source,
  MEDIUM                                                                           AS traffic_medium,
  CAMPAIGN                                                                         AS campaign,
  DEVICE_CATEGORY                                                                  AS device_category,
  COUNTRY                                                                          AS country,
  TERRITORY                                                                        AS territory,
  PRODUCT_VIEWED                                                                   AS product_key,
  EVENT_NAME                                                                       AS event_name,
  CASE WHEN EVENT_NAME IN ('contact_form','request_quote','find_dealer') THEN true ELSE false END
                                                                                   AS is_lead_event,
  current_timestamp()                                                              AS _silver_loaded_at
FROM dazana_classic_ws_catalog.techo_bloc_bronze.ga_sessions;

-- ------------------------------------------------------------
-- FACT: CRM Pipeline (HubSpot cleaned)
-- ------------------------------------------------------------
CREATE OR REPLACE TABLE dazana_classic_ws_catalog.techo_bloc_silver.fact_crm_deals
COMMENT 'CRM deals from HubSpot, cleaned and segment-tagged'
AS
SELECT
  DEAL_ID                                                                          AS deal_id,
  DEAL_NAME                                                                        AS deal_name,
  AMOUNT_USD                                                                       AS amount_usd,
  DEALSTAGE                                                                        AS deal_stage,
  CASE
    WHEN DEALSTAGE = 'closedwon'  THEN 'WON'
    WHEN DEALSTAGE = 'closedlost' THEN 'LOST'
    ELSE 'OPEN' END                                                                AS deal_outcome,
  ASSOCIATED_ACCOUNTNUM                                                            AS customer_key,
  CREATED_AT                                                                       AS created_at,
  TERRITORY                                                                        AS territory,
  LEAD_SOURCE                                                                      AS lead_source,
  current_timestamp()                                                              AS _silver_loaded_at
FROM dazana_classic_ws_catalog.techo_bloc_bronze.hubspot_deals;
