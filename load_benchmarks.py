#!/usr/bin/env python3
"""Load 12 benchmark Q+SQL pairs into the Genie space.

Creates curated_questions with question_type=BENCHMARK so they appear in the
Benchmarks tab of the Genie space UI. The SQL answer is what we expect Genie to
produce; we store it in answer_text so it stays attached to the question.
"""
import json
import subprocess

PROFILE = "Dazana-classic-ws-pat"
SPACE_ID = "01f143e3caf119e3b09d967d4ef4fc91"

BENCHMARKS = [
    ("What is our total net revenue by product line over the last year?", """
SELECT MEASURE(`Net Revenue`) AS net_revenue, `Product Line`
FROM dazana_classic_ws_catalog.techo_bloc_gold.metrics_techo_bloc
WHERE `Invoice Month` >= add_months(date_trunc('MONTH', current_date()), -12)
GROUP BY `Product Line`
ORDER BY net_revenue DESC
"""),
    ("Which territory has the highest gross margin %?", """
WITH t AS (
  SELECT `Territory`, MEASURE(`Gross Margin Pct`) AS gross_margin_pct
  FROM dazana_classic_ws_catalog.techo_bloc_gold.metrics_techo_bloc
  WHERE `Territory` IS NOT NULL
  GROUP BY `Territory`
)
SELECT * FROM t ORDER BY gross_margin_pct DESC LIMIT 1
"""),
    ("Show me the top 10 customers by lifetime revenue, broken out by segment.", """
SELECT customer_name, customer_segment, territory, lifetime_revenue_usd, lifetime_invoices, open_pipeline_usd
FROM dazana_classic_ws_catalog.techo_bloc_gold.vw_customer_360
ORDER BY lifetime_revenue_usd DESC
LIMIT 10
"""),
    ("What is the AR aging across all customers, by territory?", """
SELECT c.territory, a.aging_bucket,
       SUM(a.outstanding_usd) AS outstanding_usd,
       SUM(a.invoice_count)   AS invoice_count
FROM dazana_classic_ws_catalog.techo_bloc_gold.vw_ar_aging a
JOIN dazana_classic_ws_catalog.techo_bloc_silver.dim_customer c USING (customer_key)
GROUP BY c.territory, a.aging_bucket
ORDER BY c.territory, a.aging_bucket
"""),
    ("How does revenue from D365_FO compare to AX_2012 over the last 24 months?", """
SELECT date_trunc('MONTH', invoice_date) AS month,
       source_system,
       ROUND(SUM(net_invoice_amount), 2) AS net_revenue
FROM dazana_classic_ws_catalog.techo_bloc_silver.fact_invoice_lines
WHERE invoice_date >= add_months(date_trunc('MONTH', current_date()), -24)
GROUP BY 1, 2
ORDER BY 1
"""),
    ("Which campaigns drove the most quote-request events in 2026?", """
SELECT campaign,
       SUM(CASE WHEN event_name = 'request_quote' THEN 1 ELSE 0 END) AS quote_requests
FROM dazana_classic_ws_catalog.techo_bloc_silver.fact_web_engagement
WHERE session_date >= '2026-01-01' AND session_date < '2027-01-01'
GROUP BY campaign
ORDER BY quote_requests DESC
"""),
    ("What's the gross margin trend, monthly, by product line?", """
SELECT MEASURE(`Net Revenue`)     AS net_revenue,
       MEASURE(`Gross Margin Pct`) AS gm_pct,
       `Invoice Month`,
       `Product Line`
FROM dazana_classic_ws_catalog.techo_bloc_gold.metrics_techo_bloc
GROUP BY `Invoice Month`, `Product Line`
ORDER BY `Invoice Month`, `Product Line`
"""),
    ("Which contractors had open pipeline > $100K but no invoice activity in the last 90 days?", """
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
"""),
    ("What's our discount % by customer segment this year?", """
SELECT MEASURE(`Discount Pct`) AS discount_pct,
       `Customer Segment`
FROM dazana_classic_ws_catalog.techo_bloc_gold.metrics_techo_bloc
WHERE `Invoice Year` = year(current_date())
GROUP BY `Customer Segment`
ORDER BY discount_pct DESC
"""),
    ("Show GL spend by category over the last 5 years (revenue, COGS, OpEx, CapEx).", """
SELECT date_trunc('YEAR', transaction_date) AS year,
       gl_category,
       ROUND(SUM(CASE WHEN gl_category='REVENUE' THEN -amount_usd ELSE amount_usd END), 2) AS amount_usd
FROM dazana_classic_ws_catalog.techo_bloc_silver.fact_gl_transactions
WHERE transaction_date >= add_months(current_date(), -60)
GROUP BY 1, 2
ORDER BY 1, 2
"""),
    ("Which products had the largest year-over-year revenue growth?", """
WITH yearly AS (
  SELECT p.product_key, p.product_name, p.product_line,
         year(f.invoice_date) AS yr,
         SUM(f.net_invoice_amount) AS net_rev
  FROM dazana_classic_ws_catalog.techo_bloc_silver.fact_invoice_lines f
  JOIN dazana_classic_ws_catalog.techo_bloc_silver.dim_product p USING (product_key)
  GROUP BY 1,2,3,4
)
SELECT product_name, product_line, yr, net_rev,
       LAG(net_rev) OVER (PARTITION BY product_key ORDER BY yr) AS prev_year_net_rev,
       net_rev - LAG(net_rev) OVER (PARTITION BY product_key ORDER BY yr) AS yoy_growth_usd
FROM yearly
QUALIFY yoy_growth_usd IS NOT NULL
ORDER BY yoy_growth_usd DESC
LIMIT 50
"""),
    ("What share of revenue comes from each customer segment, by territory?", """
WITH s AS (
  SELECT MEASURE(`Net Revenue`) AS net_revenue,
         `Customer Segment`,
         `Territory`
  FROM dazana_classic_ws_catalog.techo_bloc_gold.metrics_techo_bloc
  GROUP BY `Customer Segment`, `Territory`
)
SELECT `Territory`, `Customer Segment`, net_revenue,
       net_revenue / SUM(net_revenue) OVER (PARTITION BY `Territory`) AS share_of_territory
FROM s
ORDER BY `Territory`, share_of_territory DESC
"""),
]


def api(method, path, body=None):
    cmd = ["databricks", "api", method, path, f"--profile={PROFILE}"]
    if body is not None:
        cmd.append(f"--json={json.dumps(body)}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{r.stderr}\n{r.stdout}")
    return json.loads(r.stdout) if r.stdout.strip() else {}


def main():
    # Drop any existing BENCHMARK rows so we don't double-load
    existing = api("get", f"/api/2.0/data-rooms/{SPACE_ID}/curated-questions")
    for q in (existing.get("curated_questions") or []):
        if q.get("question_type") == "BENCHMARK":
            api("delete", f"/api/2.0/data-rooms/{SPACE_ID}/curated-questions/{q['curated_question_id']}")

    print(f"Loading {len(BENCHMARKS)} benchmarks...")
    for question, sql in BENCHMARKS:
        body = {
            "curated_question": {
                "question_text": question,
                "question_type": "BENCHMARK",
                "answer_text": sql.strip(),
            }
        }
        api("post", f"/api/2.0/data-rooms/{SPACE_ID}/curated-questions", body)
        print(f"  + {question[:80]}")

    # Verify
    listing = api("get", f"/api/2.0/data-rooms/{SPACE_ID}/curated-questions")
    bms = [q for q in (listing.get("curated_questions") or []) if q.get("question_type") == "BENCHMARK"]
    print(f"\nBenchmarks now in space: {len(bms)}")


if __name__ == "__main__":
    main()
