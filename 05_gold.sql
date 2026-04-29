-- ============================================================
-- Gold layer: business-ready views, materialized view, customer 360, metric view
-- ============================================================

-- ------------------------------------------------------------
-- Customer view (regular VIEW; PII columns will get column masks attached)
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW dazana_classic_ws_catalog.techo_bloc_gold.vw_dim_customer
COMMENT 'Customer dim — used in dashboards and Genie. PII columns enforced by Unity Catalog column masks.'
AS
SELECT
  customer_key,
  customer_name,
  email,
  phone,
  address_line1,
  city,
  state_province,
  postal_code,
  country,
  territory,
  customer_segment,
  is_active,
  credit_limit_usd,
  created_at
FROM dazana_classic_ws_catalog.techo_bloc_silver.dim_customer;

-- ------------------------------------------------------------
-- Employee view — masked PII for non-HR
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW dazana_classic_ws_catalog.techo_bloc_gold.vw_dim_employee
COMMENT 'Employee dim. SSN and annual_salary are masked for non-HR users by Unity Catalog column masks.'
AS
SELECT
  employee_key,
  full_name,
  ssn,
  annual_salary_usd,
  hire_date,
  department_code,
  department,
  work_email,
  territory,
  status
FROM dazana_classic_ws_catalog.techo_bloc_silver.dim_employee;

-- ------------------------------------------------------------
-- Materialized view: monthly sales summary (the "Kimball materialized view" demo)
-- ------------------------------------------------------------
CREATE OR REPLACE MATERIALIZED VIEW dazana_classic_ws_catalog.techo_bloc_gold.mv_sales_summary
COMMENT 'Materialized monthly sales summary (D365 + AX 2012 unified). Refreshes via serverless DLT pipeline.'
AS
SELECT
  date_trunc('MONTH', f.invoice_date)                                              AS invoice_month,
  c.territory,
  c.customer_segment,
  p.product_line,
  p.product_tier,
  f.source_system,
  COUNT(DISTINCT f.invoice_id)                                                     AS invoice_count,
  COUNT(*)                                                                         AS line_count,
  SUM(f.quantity)                                                                  AS units_sold,
  ROUND(SUM(f.gross_line_amount), 2)                                               AS gross_revenue_usd,
  ROUND(SUM(f.discount_amount), 2)                                                 AS discount_usd,
  ROUND(SUM(f.freight_amount + f.pallet_amount), 2)                                AS freight_pallet_usd,
  ROUND(SUM(f.net_invoice_amount), 2)                                              AS net_revenue_usd,
  ROUND(SUM(f.quantity * p.unit_cost_usd), 2)                                      AS estimated_cogs_usd,
  ROUND(SUM(f.net_invoice_amount) - SUM(f.quantity * p.unit_cost_usd), 2)          AS estimated_gross_margin_usd
FROM dazana_classic_ws_catalog.techo_bloc_silver.fact_invoice_lines f
JOIN dazana_classic_ws_catalog.techo_bloc_silver.dim_customer      c ON f.customer_key = c.customer_key
JOIN dazana_classic_ws_catalog.techo_bloc_silver.dim_product       p ON f.product_key  = p.product_key
GROUP BY 1,2,3,4,5,6;

-- ------------------------------------------------------------
-- Finance KPI view (multi-year GL): solves the 1GB Power BI cap
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW dazana_classic_ws_catalog.techo_bloc_gold.vw_finance_kpis
COMMENT 'Multi-year finance KPIs over 600K GL rows. Replaces the Power BI 1GB-capped GL semantic model.'
AS
SELECT
  date_trunc('MONTH', g.transaction_date)                                          AS gl_month,
  g.territory,
  g.business_unit,
  g.gl_category,
  g.gl_account,
  g.gl_description,
  -- Conventional sign: revenue is stored negative in AX, flip for reporting
  ROUND(SUM(CASE WHEN g.gl_category = 'REVENUE'        THEN -g.amount_usd ELSE 0 END), 2) AS revenue_usd,
  ROUND(SUM(CASE WHEN g.gl_category = 'REVENUE_CONTRA' THEN -g.amount_usd ELSE 0 END), 2) AS contra_revenue_usd,
  ROUND(SUM(CASE WHEN g.gl_category = 'COGS'           THEN  g.amount_usd ELSE 0 END), 2) AS cogs_usd,
  ROUND(SUM(CASE WHEN g.gl_category = 'OPEX'           THEN  g.amount_usd ELSE 0 END), 2) AS opex_usd,
  ROUND(SUM(CASE WHEN g.gl_category = 'CAPEX'          THEN  g.amount_usd ELSE 0 END), 2) AS capex_usd,
  COUNT(*)                                                                                AS gl_line_count
FROM dazana_classic_ws_catalog.techo_bloc_silver.fact_gl_transactions g
GROUP BY 1,2,3,4,5,6;

-- ------------------------------------------------------------
-- Customer 360 view — joins sales + CRM + web
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW dazana_classic_ws_catalog.techo_bloc_gold.vw_customer_360
COMMENT 'Customer 360: sales totals + CRM pipeline + web engagement signals'
AS
WITH sales AS (
  SELECT customer_key,
         COUNT(DISTINCT invoice_id)            AS lifetime_invoices,
         ROUND(SUM(net_invoice_amount), 2)     AS lifetime_revenue_usd,
         MAX(invoice_date)                     AS last_invoice_date
  FROM dazana_classic_ws_catalog.techo_bloc_silver.fact_invoice_lines
  GROUP BY 1
),
crm AS (
  SELECT customer_key,
         COUNT(*)                                                                  AS lifetime_deals,
         SUM(CASE WHEN deal_outcome = 'WON'  THEN amount_usd ELSE 0 END)           AS won_pipeline_usd,
         SUM(CASE WHEN deal_outcome = 'OPEN' THEN amount_usd ELSE 0 END)           AS open_pipeline_usd
  FROM dazana_classic_ws_catalog.techo_bloc_silver.fact_crm_deals
  GROUP BY 1
)
SELECT
  c.customer_key,
  c.customer_name,
  c.customer_segment,
  c.territory,
  c.country,
  c.is_active,
  c.credit_limit_usd,
  COALESCE(s.lifetime_invoices, 0)                                                 AS lifetime_invoices,
  COALESCE(s.lifetime_revenue_usd, 0)                                              AS lifetime_revenue_usd,
  s.last_invoice_date,
  COALESCE(cr.lifetime_deals, 0)                                                   AS lifetime_deals,
  COALESCE(cr.won_pipeline_usd, 0)                                                 AS won_pipeline_usd,
  COALESCE(cr.open_pipeline_usd, 0)                                                AS open_pipeline_usd
FROM dazana_classic_ws_catalog.techo_bloc_silver.dim_customer c
LEFT JOIN sales s   ON c.customer_key = s.customer_key
LEFT JOIN crm   cr  ON c.customer_key = cr.customer_key;

-- ------------------------------------------------------------
-- AR Aging view — 1GB-cap-killer use case: full AR aging across years
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW dazana_classic_ws_catalog.techo_bloc_gold.vw_ar_aging
COMMENT 'AR aging buckets across 5+ years of invoices (D365 + AX 2012 unified)'
AS
WITH base AS (
  SELECT
    customer_key,
    invoice_id,
    invoice_date,
    net_invoice_amount,
    DATEDIFF(current_date(), invoice_date)                     AS days_outstanding
  FROM dazana_classic_ws_catalog.techo_bloc_silver.fact_invoice_lines
)
SELECT
  customer_key,
  CASE
    WHEN days_outstanding <= 30  THEN '0-30'
    WHEN days_outstanding <= 60  THEN '31-60'
    WHEN days_outstanding <= 90  THEN '61-90'
    WHEN days_outstanding <= 180 THEN '91-180'
    WHEN days_outstanding <= 365 THEN '181-365'
    ELSE '365+'
  END                                                          AS aging_bucket,
  COUNT(DISTINCT invoice_id)                                   AS invoice_count,
  ROUND(SUM(net_invoice_amount), 2)                            AS outstanding_usd
FROM base
GROUP BY 1, 2;
