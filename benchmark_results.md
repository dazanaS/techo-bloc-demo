# Techo-Bloc Genie Benchmark

- Space: `01f143e3caf119e3b09d967d4ef4fc91`
- Warehouse: `a82088b3bfe8752c` (Serverless Starter, Small)
- Questions: **12** • Completed: **12** • Failed: **0**
- Latency — avg: **12.0s** • p50: **11.2s** • p95: **19.2s**

## Per-question results

| # | Label | Status | Latency | Rows | Question |
|---|---|---|---:|---:|---|
| 1 | `kpi_metric_view` | COMPLETED | 11.1s | 3 | What is our total net revenue by product line over the last year? |
| 2 | `kpi_margin` | COMPLETED | 14.5s | 1 | Which territory has the highest gross margin %? |
| 3 | `top_customers` | COMPLETED | 11.2s | 10 | Show me the top 10 customers by lifetime revenue, broken out by segment. |
| 4 | `ar_aging` | COMPLETED | 11.1s | 24 | What is the AR aging across all customers, by territory? |
| 5 | `system_split` | COMPLETED | 11.2s | 16 | How does revenue from D365_FO compare to AX_2012 over the last 24 months? |
| 6 | `campaigns` | COMPLETED | 7.8s | 6 | Which campaigns drove the most quote-request events in 2026? |
| 7 | `trend` | COMPLETED | 11.1s | 140 | What's the gross margin trend, monthly, by product line? |
| 8 | `complex_join` | COMPLETED | 11.7s | 808 | Which contractors had open pipeline > $100K but no invoice activity in the last 90 days? |
| 9 | `discount_segment` | COMPLETED | 11.1s | 2 | What's our discount % by customer segment this year? |
| 10 | `gl_5yr` | COMPLETED | 11.2s | 16 | Show GL spend by category over the last 5 years (revenue, COGS, OpEx, CapEx). |
| 11 | `yoy_growth` | COMPLETED | 18.0s | 990 | Which products had the largest year-over-year revenue growth? |
| 12 | `share_segment` | COMPLETED | 14.5s | 5 | What share of revenue comes from each customer segment, by territory? |

## SQL produced by Genie

### 1. kpi_metric_view — _What is our total net revenue by product line over the last year?_
**status:** COMPLETED • **latency:** 11.1s • **rows:** 3

```sql
SELECT MEASURE(`Net Revenue`) AS net_revenue, `Product Line`
FROM dazana_classic_ws_catalog.techo_bloc_gold.metrics_techo_bloc
WHERE `Invoice Month` >= add_months(date_trunc('MONTH', current_date()), -12)
GROUP BY `Product Line`
ORDER BY net_revenue DESC
```

### 2. kpi_margin — _Which territory has the highest gross margin %?_
**status:** COMPLETED • **latency:** 14.5s • **rows:** 1

```sql
WITH territory_gm AS (SELECT `Territory`, MEASURE(`Gross Margin Pct`) AS gross_margin_pct FROM dazana_classic_ws_catalog.techo_bloc_gold.metrics_techo_bloc GROUP BY `Territory`), ranked_territory AS (SELECT `Territory`, gross_margin_pct, RANK() OVER (ORDER BY gross_margin_pct DESC) AS rank FROM territory_gm) SELECT `Territory`, gross_margin_pct FROM ranked_territory WHERE rank = 1
```

### 3. top_customers — _Show me the top 10 customers by lifetime revenue, broken out by segment._
**status:** COMPLETED • **latency:** 11.2s • **rows:** 10

```sql
SELECT customer_name, customer_segment, territory, lifetime_revenue_usd, lifetime_invoices, open_pipeline_usd
FROM dazana_classic_ws_catalog.techo_bloc_gold.vw_customer_360
ORDER BY lifetime_revenue_usd DESC
LIMIT 10
```

### 4. ar_aging — _What is the AR aging across all customers, by territory?_
**status:** COMPLETED • **latency:** 11.1s • **rows:** 24

```sql
SELECT c.territory,
       a.aging_bucket,
       SUM(a.outstanding_usd) AS outstanding_usd,
       SUM(a.invoice_count)   AS invoice_count
FROM dazana_classic_ws_catalog.techo_bloc_gold.vw_ar_aging a
JOIN dazana_classic_ws_catalog.techo_bloc_silver.dim_customer c USING (customer_key)
WHERE c.territory IS NOT NULL AND a.aging_bucket IS NOT NULL
GROUP BY c.territory, a.aging_bucket
ORDER BY c.territory,
  CASE a.aging_bucket WHEN '0-30' THEN 1 WHEN '31-60' THEN 2 WHEN '61-90' THEN 3
                      WHEN '91-180' THEN 4 WHEN '181-365' THEN 5 ELSE 6 END
```

### 5. system_split — _How does revenue from D365_FO compare to AX_2012 over the last 24 months?_
**status:** COMPLETED • **latency:** 11.2s • **rows:** 16

```sql
SELECT date_trunc('MONTH', `invoice_date`) AS `month`,
       `source_system`,
       ROUND(SUM(`net_invoice_amount`), 2) AS `net_revenue`
FROM `dazana_classic_ws_catalog`.`techo_bloc_silver`.`fact_invoice_lines`
WHERE `invoice_date` >= add_months(date_trunc('MONTH', current_date()), -24)
GROUP BY 1, 2
ORDER BY 1, 2
```

### 6. campaigns — _Which campaigns drove the most quote-request events in 2026?_
**status:** COMPLETED • **latency:** 7.8s • **rows:** 6

```sql
SELECT campaign, COUNT(*) AS quote_requests
FROM dazana_classic_ws_catalog.techo_bloc_silver.fact_web_engagement
WHERE session_date >= '2026-01-01' AND event_name = 'request_quote'
GROUP BY campaign
ORDER BY quote_requests DESC
```

### 7. trend — _What's the gross margin trend, monthly, by product line?_
**status:** COMPLETED • **latency:** 11.1s • **rows:** 140

```sql
SELECT DATE_TRUNC('MONTH', `Invoice Month`) AS month, 
       `Product Line`, 
       MEASURE(`Gross Margin Pct`) AS gross_margin_pct
FROM dazana_classic_ws_catalog.techo_bloc_gold.metrics_techo_bloc
WHERE `Invoice Month` IS NOT NULL AND `Product Line` IS NOT NULL
GROUP BY ALL
ORDER BY month, `Product Line`
```

### 8. complex_join — _Which contractors had open pipeline > $100K but no invoice activity in the last 90 days?_
**status:** COMPLETED • **latency:** 11.7s • **rows:** 808

```sql
WITH last_invoice AS (
  SELECT customer_key, MAX(invoice_date) AS last_invoice_date
  FROM dazana_classic_ws_catalog.techo_bloc_silver.fact_invoice_lines
  GROUP BY customer_key
),
open_p AS (
  SELECT customer_key, SUM(amount_usd) AS open_pipeline_usd
  FROM dazana_classic_ws_catalog.techo_bloc_silver.fact_crm_deals
  WHERE deal_outcome = 'OPEN'
  GROUP BY customer_key
)
SELECT c.customer_name, c.territory, op.open_pipeline_usd, li.last_invoice_date
FROM open_p op
JOIN dazana_classic_ws_catalog.techo_bloc_silver.dim_customer c USING (customer_key)
LEFT JOIN last_invoice li USING (customer_key)
WHERE c.customer_segment = 'CONTRACTOR'
  AND op.open_pipeline_usd > 100000
  AND (li.last_invoice_date IS NULL OR li.last_invoice_date < date_sub(current_date(), 90))
ORDER BY op.open_pipeline_usd DESC
```

### 9. discount_segment — _What's our discount % by customer segment this year?_
**status:** COMPLETED • **latency:** 11.1s • **rows:** 2

```sql
SELECT MEASURE(`Discount Pct`) AS discount_pct, `Customer Segment` FROM dazana_classic_ws_catalog.techo_bloc_gold.metrics_techo_bloc WHERE YEAR(`Invoice Month`) = 2026 AND `Customer Segment` IS NOT NULL GROUP BY `Customer Segment`
HAVING discount_pct IS NOT NULL ORDER BY discount_pct DESC
```

### 10. gl_5yr — _Show GL spend by category over the last 5 years (revenue, COGS, OpEx, CapEx)._
**status:** COMPLETED • **latency:** 11.2s • **rows:** 16

```sql
SELECT date_trunc('YEAR', `transaction_date`) AS `year`,
       `gl_category`,
       ROUND(SUM(CASE WHEN `gl_category` = 'REVENUE' THEN -`amount_usd` ELSE `amount_usd` END), 2) AS `amount_usd`
FROM `dazana_classic_ws_catalog`.`techo_bloc_silver`.`fact_gl_transactions`
WHERE `transaction_date` >= '2021-01-01'
  AND `gl_category` IN ('REVENUE', 'COGS', 'OPEX', 'CAPEX')
GROUP BY 1, 2
ORDER BY 1, 2
```

### 11. yoy_growth — _Which products had the largest year-over-year revenue growth?_
**status:** COMPLETED • **latency:** 18.0s • **rows:** 990

```sql
WITH yearly_revenue AS (
  SELECT date_trunc('YEAR', f.invoice_date) AS year,
         f.product_key,
         p.product_name,
         SUM(f.net_invoice_amount) AS revenue
  FROM dazana_classic_ws_catalog.techo_bloc_silver.fact_invoice_lines f
  JOIN dazana_classic_ws_catalog.techo_bloc_silver.dim_product p
    ON f.product_key = p.product_key
  WHERE f.product_key IS NOT NULL AND p.product_name IS NOT NULL
  GROUP BY year, f.product_key, p.product_name
),
revenue_growth AS (
  SELECT year,
         product_key,
         product_name,
         revenue,
         LAG(revenue) OVER (PARTITION BY product_key ORDER BY year) AS prev_year_revenue,
         TRY_DIVIDE(revenue - LAG(revenue) OVER (PARTITION BY product_key ORDER BY year), LAG(revenue) OVER (PARTITION BY product_key ORDER BY year)) * 100 AS yoy_growth_pct
  FROM yearly_revenue
)
SELECT year, product_key, product_name, revenue, yoy_growth_pct
FROM revenue_growth
WHERE prev_year_revenue IS NOT NULL
ORDER BY yoy_growth_pct DESC
```

### 12. share_segment — _What share of revenue comes from each customer segment, by territory?_
**status:** COMPLETED • **latency:** 14.5s • **rows:** 5

```sql
WITH segment_revenue AS (
  SELECT `Customer Segment`, `Territory`, MEASURE(`Net Revenue`) AS segment_net_revenue
  FROM dazana_classic_ws_catalog.techo_bloc_gold.metrics_techo_bloc
  WHERE `Customer Segment` IS NOT NULL AND `Territory` IS NOT NULL
  GROUP BY ALL
),
territory_total AS (
  SELECT `Territory`, MEASURE(`Net Revenue`) AS territory_net_revenue
  FROM dazana_classic_ws_catalog.techo_bloc_gold.metrics_techo_bloc
  WHERE `Territory` IS NOT NULL
  GROUP BY ALL
)
SELECT s.`Customer Segment`, s.`Territory`, s.segment_net_revenue, t.territory_net_revenue,
       try_divide(s.segment_net_revenue,t.territory_net_revenue) AS revenue_share
FROM segment_revenue s
JOIN territory_total t ON s.`Territory` = t.`Territory`
ORDER BY s.`Territory`, revenue_share DESC
```
