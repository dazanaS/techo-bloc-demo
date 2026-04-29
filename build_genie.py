#!/usr/bin/env python3
"""Populate the Techo-Bloc Genie space with curated questions, instructions, and SQL examples."""
import json
import subprocess

PROFILE = "Dazana-classic-ws-pat"
SPACE_ID = "01f143e3caf119e3b09d967d4ef4fc91"


def api(method, path, body=None):
    cmd = ["databricks", "api", method, path, f"--profile={PROFILE}"]
    if body is not None:
        cmd.append(f"--json={json.dumps(body)}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{r.stderr}\n{r.stdout}")
    return json.loads(r.stdout) if r.stdout.strip() else {}


# ---------------- Curated questions ----------------
QUESTIONS = [
    "What is our total net revenue by product line over the last year?",
    "Which territory has the highest gross margin %?",
    "Show me the top 10 customers by lifetime revenue, broken out by segment.",
    "What is the AR aging across all customers, by territory?",
    "How does revenue from D365_FO compare to AX_2012 over the last 24 months?",
    "Which campaigns drove the most quote-request events in 2026?",
    "What's the gross margin trend, monthly, by product line?",
    "Which contractors had open pipeline > $100K but no invoice activity in the last 90 days?",
    "What's our discount % by customer segment this year?",
    "Show GL spend by category over the last 5 years (revenue, COGS, OpEx, CapEx).",
    "Which products had the largest year-over-year revenue growth?",
    "What share of revenue comes from each customer segment, by territory?",
]

# ---------------- General (text) instructions ----------------
TEXT_INSTRUCTIONS = [
    ("Prefer the metric view for KPIs",
     "When a user asks about Net Revenue, Gross Margin Pct, Discount Pct, Average Invoice Value, "
     "Active Customers, or any KPI, query the metric view "
     "`dazana_classic_ws_catalog.techo_bloc_gold.metrics_techo_bloc` using MEASURE() syntax. "
     "Example: SELECT MEASURE(`Net Revenue`), `Product Line` FROM techo_bloc_gold.metrics_techo_bloc GROUP BY `Product Line`. "
     "This guarantees KPI consistency across BI tools."),

    ("Time anchoring",
     "Invoice data covers 2019-01-01 through 2026 (AX 2012 from 2019-2024, D365_FO from 2025+). "
     "When the user says 'this year' or 'last year', use the actual data range — not current_date(). "
     "Use date_trunc('MONTH', invoice_date) for monthly trends and date_trunc('QUARTER', invoice_date) for quarterly."),

    ("Source system distinction",
     "source_system = 'D365_FO' is the current ERP (post-cutover). source_system = 'AX_2012' is the legacy on-prem ERP. "
     "When users ask about historical or 'pre-migration' data, filter source_system = 'AX_2012'. "
     "When unifying, do NOT filter — fact_invoice_lines is already the unified table."),

    ("GL revenue sign convention",
     "In fact_gl_transactions, revenue rows (gl_category = 'REVENUE') are stored with NEGATIVE amount_usd "
     "due to AX 2012 debit/credit convention. Always flip with -amount_usd or use vw_finance_kpis which already handles this."),

    ("Customer segment values",
     "customer_segment is uppercase: HOMEOWNER, CONTRACTOR, COMMERCIAL. "
     "HOMEOWNER = DIY residential, CONTRACTOR = Techo-Pro loyalty members, COMMERCIAL = developers/projects."),

    ("Territory and RLS",
     "Territory values: US-East, US-West, Canada-East, Canada-West. "
     "fact_gl_transactions and dim_customer have territory-based row-level filters. "
     "If a user is a regional manager, they will only see their territory automatically."),

    ("PII fields are masked",
     "dim_customer.email, .phone, .address_line1 and dim_employee.ssn, .annual_salary_usd are masked "
     "for non-HR/non-Finance users. Do NOT try to bypass this; show the masked values as-is."),

    ("Joining facts to dims",
     "fact_invoice_lines.customer_key → dim_customer.customer_key, "
     "fact_invoice_lines.product_key → dim_product.product_key, "
     "fact_crm_deals.customer_key → dim_customer.customer_key, "
     "fact_web_engagement.product_key → dim_product.product_key. "
     "Always alias the dim/fact tables (e.g., `f`, `c`, `p`) for clarity."),
]

# ---------------- SQL examples (trusted assets) ----------------
SQL_INSTRUCTIONS = [
    ("Net Revenue by product line — last 12 months",
     """SELECT MEASURE(`Net Revenue`)        AS net_revenue,
       MEASURE(`Gross Margin Pct`)    AS gm_pct,
       `Product Line`
FROM dazana_classic_ws_catalog.techo_bloc_gold.metrics_techo_bloc
WHERE `Invoice Month` >= add_months(date_trunc('MONTH', current_date()), -12)
GROUP BY `Product Line`
ORDER BY net_revenue DESC"""),

    ("Top 10 customers by lifetime revenue with segment",
     """SELECT customer_name, customer_segment, territory,
       lifetime_revenue_usd, lifetime_invoices, open_pipeline_usd
FROM dazana_classic_ws_catalog.techo_bloc_gold.vw_customer_360
ORDER BY lifetime_revenue_usd DESC
LIMIT 10"""),

    ("AR aging by territory",
     """SELECT c.territory,
       a.aging_bucket,
       SUM(a.outstanding_usd) AS outstanding_usd,
       SUM(a.invoice_count)   AS invoice_count
FROM dazana_classic_ws_catalog.techo_bloc_gold.vw_ar_aging a
JOIN dazana_classic_ws_catalog.techo_bloc_silver.dim_customer c USING (customer_key)
GROUP BY c.territory, a.aging_bucket
ORDER BY c.territory,
  CASE a.aging_bucket WHEN '0-30' THEN 1 WHEN '31-60' THEN 2 WHEN '61-90' THEN 3
                      WHEN '91-180' THEN 4 WHEN '181-365' THEN 5 ELSE 6 END"""),

    ("D365 vs AX 2012 monthly revenue split",
     """SELECT date_trunc('MONTH', invoice_date) AS month,
       source_system,
       ROUND(SUM(net_invoice_amount), 2)  AS net_revenue
FROM dazana_classic_ws_catalog.techo_bloc_silver.fact_invoice_lines
WHERE invoice_date >= add_months(date_trunc('MONTH', current_date()), -24)
GROUP BY 1, 2
ORDER BY 1"""),

    ("Multi-year GL: revenue / COGS / OpEx",
     """SELECT date_trunc('YEAR', transaction_date) AS year,
       gl_category,
       ROUND(SUM(CASE WHEN gl_category = 'REVENUE' THEN -amount_usd ELSE amount_usd END), 2) AS amount_usd
FROM dazana_classic_ws_catalog.techo_bloc_silver.fact_gl_transactions
GROUP BY 1, 2
ORDER BY 1, 2"""),

    ("Campaign → quote conversion",
     """SELECT campaign,
       COUNT(*)                                                                AS sessions,
       SUM(CASE WHEN event_name = 'request_quote' THEN 1 ELSE 0 END)           AS quotes,
       ROUND(SUM(CASE WHEN event_name='request_quote' THEN 1 ELSE 0 END)*100.0 /
             NULLIF(COUNT(*),0), 2)                                            AS quote_conv_pct
FROM dazana_classic_ws_catalog.techo_bloc_silver.fact_web_engagement
WHERE session_date >= '2026-01-01'
GROUP BY campaign
ORDER BY quotes DESC"""),

    ("Customer segments × territory revenue mix",
     """SELECT MEASURE(`Net Revenue`) AS net_revenue,
       `Customer Segment`,
       `Territory`
FROM dazana_classic_ws_catalog.techo_bloc_gold.metrics_techo_bloc
GROUP BY `Customer Segment`, `Territory`
ORDER BY `Territory`, net_revenue DESC"""),

    ("Contractors with open pipeline but no recent invoices",
     """WITH last_invoice AS (
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
ORDER BY op.open_pipeline_usd DESC"""),
]


def main():
    # --- Curated questions ---
    print("Adding curated questions...")
    for q in QUESTIONS:
        api("post", f"/api/2.0/data-rooms/{SPACE_ID}/curated-questions",
            {"curated_question": {"question_text": q}})
    print(f"  added {len(QUESTIONS)}")

    # --- Text instructions ---
    print("Adding text instructions...")
    for title, content in TEXT_INSTRUCTIONS:
        api("post", f"/api/2.0/data-rooms/{SPACE_ID}/instructions",
            {"title": title, "content": content, "instruction_type": "TEXT_INSTRUCTION"})
    print(f"  added {len(TEXT_INSTRUCTIONS)}")

    # --- SQL examples ---
    print("Adding SQL examples...")
    for title, sql in SQL_INSTRUCTIONS:
        api("post", f"/api/2.0/data-rooms/{SPACE_ID}/instructions",
            {"title": title, "content": sql, "instruction_type": "SQL_INSTRUCTION"})
    print(f"  added {len(SQL_INSTRUCTIONS)}")

    print("Done.")


if __name__ == "__main__":
    main()
