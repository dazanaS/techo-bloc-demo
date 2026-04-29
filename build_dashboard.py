#!/usr/bin/env python3
"""Build the Techo-Bloc multi-page AI/BI dashboard.

Pages:
  1. Executive Overview     — Matt / CFO / CEO
  2. Sales Performance      — Sales leaders, regional managers
  3. Finance & GL Deep-Dive — Finance team (the 1 GB Power BI cap killer)
  4. Marketing & Web        — Marketing / GTM
  5. Customer 360           — Account managers

Each page has top-row filter widgets (date range + segment / territory /
campaign / etc.) wired with the `associative_filter_predicate_group`
pattern so Lakeview cross-filters every chart on the page when the user
clicks a bar / pie slice / dropdown.

Run:
    python3 build_dashboard.py                       # create new dashboard
    python3 build_dashboard.py <dashboard_id>        # PATCH existing one
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid

PROFILE      = "Dazana-classic-ws-pat"
WAREHOUSE    = "a82088b3bfe8752c"
PARENT_PATH  = "/Users/dazana.hasan@databricks.com"
CATALOG      = "dazana_classic_ws_catalog"
SILVER       = f"{CATALOG}.techo_bloc_silver"
GOLD         = f"{CATALOG}.techo_bloc_gold"


def nid() -> str:
    return uuid.uuid4().hex[:8]


def safe_name(expr: str) -> str:
    return expr.lower().replace(" ", "").replace("`", "").replace('"', "")


def strip_nulls(obj):
    if isinstance(obj, dict):
        return {k: strip_nulls(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [strip_nulls(v) for v in obj]
    return obj


# ───────────────────────── widget helpers ──────────────────────────

def at(widget: dict, x: int, y: int, w: int, h: int) -> dict:
    return {**widget, "position": {"x": x, "y": y, "width": w, "height": h}}


def text(md: str) -> dict:
    return {
        "widget": {
            "name": nid(),
            "spec": {
                "version": 1,
                "widgetType": "text",
                "encodings": {},
                "text": md,
                "frame": {"showTitle": False},
            },
        }
    }


def counter(ds: str, expr: str, title: str) -> dict:
    fname = safe_name(expr)
    return {
        "widget": {
            "name": nid(),
            "queries": [{
                "name": "main_query",
                "query": {
                    "datasetName": ds,
                    "fields": [{"name": fname, "expression": expr}],
                    "disaggregated": True,
                },
            }],
            "spec": {
                "version": 2,
                "widgetType": "counter",
                "encodings": {"value": {"fieldName": fname, "displayName": title}},
                "frame": {"showTitle": True, "title": title},
            },
        }
    }


def bar(ds: str, x: tuple, y: tuple, title: str, *,
        sort: str = "y-reversed", color: tuple | None = None,
        stacking: str | None = None) -> dict:
    xn, yn = safe_name(x[0]), safe_name(y[0])
    fields = [
        {"name": xn, "expression": x[0]},
        {"name": yn, "expression": y[0]},
    ]
    encodings = {
        "x": {"fieldName": xn, "scale": {"type": "categorical", "sort": {"by": sort}}, "displayName": x[1]},
        "y": {"fieldName": yn, "scale": {"type": "quantitative"}, "displayName": y[1]},
        "label": {"show": True},
    }
    if color:
        cn = safe_name(color[0])
        fields.append({"name": cn, "expression": color[0]})
        col_enc = {"fieldName": cn, "scale": {"type": "categorical"}, "displayName": color[1]}
        if stacking:
            col_enc["stacking"] = stacking
        encodings["color"] = col_enc
    return {
        "widget": {
            "name": nid(),
            "queries": [{"name": "main_query",
                         "query": {"datasetName": ds, "fields": fields, "disaggregated": False}}],
            "spec": {
                "version": 3,
                "widgetType": "bar",
                "encodings": encodings,
                "frame": {"showTitle": True, "title": title},
            },
        }
    }


def line(ds: str, x: tuple, y: tuple, color: tuple | None, title: str, *,
         x_scale: str = "temporal") -> dict:
    xn, yn = safe_name(x[0]), safe_name(y[0])
    fields = [
        {"name": xn, "expression": x[0]},
        {"name": yn, "expression": y[0]},
    ]
    encodings = {
        "x": {"fieldName": xn, "scale": {"type": x_scale}, "displayName": x[1]},
        "y": {"fieldName": yn, "scale": {"type": "quantitative"}, "displayName": y[1]},
    }
    if color:
        cn = safe_name(color[0])
        fields.append({"name": cn, "expression": color[0]})
        encodings["color"] = {"fieldName": cn, "scale": {"type": "categorical"}, "displayName": color[1]}
    return {
        "widget": {
            "name": nid(),
            "queries": [{"name": "main_query",
                         "query": {"datasetName": ds, "fields": fields, "disaggregated": False}}],
            "spec": {
                "version": 3,
                "widgetType": "line",
                "encodings": encodings,
                "frame": {"showTitle": True, "title": title},
            },
        }
    }


def area(ds: str, x: tuple, y: tuple, color: tuple, title: str) -> dict:
    w = line(ds, x, y, color, title)
    w["widget"]["spec"]["widgetType"] = "area"
    return w


def pie(ds: str, angle_expr: str, angle_name: str,
        color_expr: str, color_name: str, title: str) -> dict:
    an, cn = safe_name(angle_expr), safe_name(color_expr)
    return {
        "widget": {
            "name": nid(),
            "queries": [{
                "name": "main_query",
                "query": {
                    "datasetName": ds,
                    "fields": [
                        {"name": an, "expression": angle_expr},
                        {"name": cn, "expression": color_expr},
                    ],
                    "disaggregated": False,
                },
            }],
            "spec": {
                "version": 3,
                "widgetType": "pie",
                "encodings": {
                    "angle": {"fieldName": an, "scale": {"type": "quantitative"}, "displayName": angle_name},
                    "color": {"fieldName": cn, "scale": {"type": "categorical"}, "displayName": color_name},
                },
                "frame": {"showTitle": True, "title": title},
            },
        }
    }


def table(ds: str, columns: list[tuple], title: str) -> dict:
    """columns: list of (expression, display_title, type, displayAs)."""
    fields, cols, used = [], [], set()
    for (expr, name, ctype, display_as) in columns:
        fname = safe_name(expr)
        base, i = fname, 1
        while fname in used:
            fname = f"{base}_{i}"; i += 1
        used.add(fname)
        fields.append({"name": fname, "expression": expr})
        col = {"fieldName": fname, "type": ctype, "displayAs": display_as,
               "title": name, "displayName": name}
        if display_as == "number":
            col["numberFormat"] = "#,##0.00"
            col["alignContent"] = "right"
        cols.append(col)
    return {
        "widget": {
            "name": nid(),
            "queries": [{"name": "main_query",
                         "query": {"datasetName": ds, "fields": fields, "disaggregated": True}}],
            "spec": {
                "version": 1,
                "widgetType": "table",
                "encodings": {"columns": cols},
                "frame": {"showTitle": True, "title": title},
            },
        }
    }


def filter_widget(widget_type: str, title: str, column: str, datasets: list[str]) -> dict:
    """Filter widget that cross-filters every dataset in `datasets`.

    Each dataset gets its own query carrying the magic `COUNT_IF(\`associative_filter_predicate_group\`)`
    field — this is how Lakeview tells the warehouse to honor active filter selections.
    """
    wid = nid()
    queries = []
    fields_enc = []
    for ds in datasets:
        qname = f"filter_{wid}_{column}_{ds}"
        queries.append({
            "name": qname,
            "query": {
                "datasetName": ds,
                "fields": [
                    {"name": column, "expression": f"`{column}`"},
                    {"name": f"{column}_associativity",
                     "expression": "COUNT_IF(`associative_filter_predicate_group`)"},
                ],
                "disaggregated": False,
            },
        })
        fields_enc.append({"fieldName": column, "displayName": column, "queryName": qname})
    return {
        "widget": {
            "name": wid,
            "queries": queries,
            "spec": {
                "version": 2,
                "widgetType": widget_type,                       # filter-multi-select / filter-single-select / filter-date-range-picker
                "encodings": {"fields": fields_enc},
                "frame": {"showTitle": True, "title": title},
            },
        }
    }


# ───────────────────────── datasets ────────────────────────────────
DATASETS: dict[str, dict] = {}
def add_ds(name: str, display: str, sql: str) -> str:
    DATASETS[name] = {"name": name, "displayName": display, "queryLines": [sql]}
    return name

# Rich invoice fact (used by Executive, Sales, Customer 360 — enables click cross-filtering)
DS_INV = add_ds("invoices", "Invoices unified (D365 + AX 2012)", f"""
SELECT
  f.invoice_id, f.line_num, f.invoice_date,
  date_trunc('MONTH',   f.invoice_date) AS invoice_month,
  date_trunc('QUARTER', f.invoice_date) AS invoice_quarter,
  YEAR(f.invoice_date)                  AS invoice_year,
  f.customer_key, f.product_key,
  f.quantity, f.unit_sales_price,
  f.gross_line_amount, f.discount_amount, f.freight_amount, f.pallet_amount,
  f.net_invoice_amount, f.tax_amount,
  f.source_system,
  c.customer_name, c.customer_segment, c.territory, c.country, c.is_active, c.credit_limit_usd,
  p.product_line, p.product_tier, p.unit_cost_usd,
  ROUND(f.quantity * p.unit_cost_usd, 2)                                         AS estimated_cogs_usd,
  ROUND(f.net_invoice_amount - (f.quantity * p.unit_cost_usd), 2)                AS estimated_gross_margin_usd
FROM {SILVER}.fact_invoice_lines f
JOIN {SILVER}.dim_customer c USING (customer_key)
JOIN {SILVER}.dim_product  p USING (product_key)
""")

# Multi-year GL (Finance page)
DS_GL = add_ds("gl", "GL transactions (5+ years)", f"""
SELECT
  voucher_id,
  transaction_date,
  date_trunc('MONTH',   transaction_date) AS gl_month,
  date_trunc('QUARTER', transaction_date) AS gl_quarter,
  YEAR(transaction_date)                  AS gl_year,
  gl_account, gl_description, gl_category, business_unit, territory,
  CASE WHEN gl_category = 'REVENUE' THEN -amount_usd ELSE amount_usd END AS amount_usd_signed,
  amount_usd                                                              AS amount_usd_raw
FROM {SILVER}.fact_gl_transactions
""")

# Web engagement (Marketing page)
DS_WEB = add_ds("web", "Web sessions (GA)", f"""
SELECT session_id, user_pseudo_id, session_date,
       date_trunc('MONTH', session_date) AS session_month,
       traffic_source, traffic_medium, campaign,
       device_category, country, territory,
       product_key, event_name, is_lead_event
FROM {SILVER}.fact_web_engagement
""")

# CRM deals (Sales / Exec page)
DS_CRM = add_ds("crm", "CRM deals (HubSpot)", f"""
SELECT deal_id, deal_name, amount_usd, deal_stage, deal_outcome,
       customer_key, created_at,
       date_trunc('MONTH', created_at) AS deal_month,
       territory, lead_source
FROM {SILVER}.fact_crm_deals
""")

# Customer 360 (precomputed) for the customer page
DS_C360 = add_ds("customers_360", "Customer 360", f"""
SELECT customer_key, customer_name, customer_segment, territory, country,
       is_active, credit_limit_usd,
       lifetime_invoices, lifetime_revenue_usd, last_invoice_date,
       lifetime_deals, won_pipeline_usd, open_pipeline_usd,
       DATEDIFF(current_date(), last_invoice_date) AS days_since_last_invoice
FROM {GOLD}.vw_customer_360
""")

# AR aging (with customer territory + segment, useful for Finance and Sales)
DS_AR = add_ds("ar", "AR Aging", f"""
SELECT a.customer_key, a.aging_bucket, a.invoice_count, a.outstanding_usd,
       c.territory, c.customer_segment, c.country
FROM {GOLD}.vw_ar_aging a
JOIN {SILVER}.dim_customer c USING (customer_key)
""")


# ───────────────────────── pages ───────────────────────────────────

def page(name: str, title: str, layout: list[dict]) -> dict:
    return {
        "name": nid(),
        "displayName": title,
        "pageType": "PAGE_TYPE_CANVAS",
        "layout": layout,
    }


# ============== PAGE 1: Executive Overview ==============
PAGE_EXEC: list[dict] = []

PAGE_EXEC.append(at(text(
    "## Executive Overview\n"
    "**Audience:** CEO, CFO, leadership.  "
    "**Source:** unified D365 F&O + AX 2012 invoice lines, governed by Unity Catalog.\n\n"
    "Headline KPIs (Net Revenue, Gross Margin %, Customers, Pipeline) update live "
    "as you click any chart segment or change a filter — Lakeview rewrites "
    "every visualization on the page in lockstep."
), 0, 0, 6, 2))

PAGE_EXEC.append(at(filter_widget("filter-date-range-picker", "Invoice date",
                                  "invoice_date", [DS_INV]),                     0, 2, 2, 2))
PAGE_EXEC.append(at(filter_widget("filter-multi-select", "Territory",
                                  "territory", [DS_INV, DS_AR, DS_C360, DS_CRM]), 2, 2, 1, 2))
PAGE_EXEC.append(at(filter_widget("filter-multi-select", "Customer Segment",
                                  "customer_segment", [DS_INV, DS_AR, DS_C360]),  3, 2, 1, 2))
PAGE_EXEC.append(at(filter_widget("filter-multi-select", "Source System",
                                  "source_system", [DS_INV]),                    4, 2, 1, 2))
PAGE_EXEC.append(at(filter_widget("filter-multi-select", "Product Line",
                                  "product_line", [DS_INV]),                     5, 2, 1, 2))

# KPI counters
PAGE_EXEC.append(at(counter(DS_INV, "SUM(`net_invoice_amount`)",  "Net Revenue"),         0, 4, 1, 3))
PAGE_EXEC.append(at(counter(DS_INV, "SUM(`estimated_gross_margin_usd`)", "Gross Margin"), 1, 4, 1, 3))
PAGE_EXEC.append(at(counter(DS_INV, "COUNT(DISTINCT `customer_key`)", "Active Customers"), 2, 4, 1, 3))
PAGE_EXEC.append(at(counter(DS_INV, "COUNT(DISTINCT `invoice_id`)",  "Invoices"),         3, 4, 1, 3))
PAGE_EXEC.append(at(counter(DS_CRM, "SUM(CASE WHEN `deal_outcome`='OPEN' THEN `amount_usd` ELSE 0 END)",
                            "Open Pipeline"),                                              4, 4, 1, 3))
PAGE_EXEC.append(at(counter(DS_INV, "AVG(`net_invoice_amount`)",     "Avg Line Value"),   5, 4, 1, 3))

# Trend
PAGE_EXEC.append(at(area(DS_INV,
    x=("`invoice_month`", "Month"),
    y=("SUM(`net_invoice_amount`)", "Net Revenue"),
    color=("`source_system`", "Source"),
    title="Monthly Net Revenue — D365 vs AX 2012 (the unification story)"
), 0, 7, 6, 5))

# Splits
PAGE_EXEC.append(at(bar(DS_INV,
    x=("`product_line`", "Product Line"),
    y=("SUM(`net_invoice_amount`)", "Net Revenue"),
    title="Net Revenue by Product Line"
), 0, 12, 3, 5))

PAGE_EXEC.append(at(bar(DS_INV,
    x=("`territory`", "Territory"),
    y=("SUM(`net_invoice_amount`)", "Net Revenue"),
    title="Net Revenue by Territory (RLS scope)"
), 3, 12, 3, 5))

PAGE_EXEC.append(at(pie(DS_INV,
    angle_expr="SUM(`net_invoice_amount`)", angle_name="Net Revenue",
    color_expr="`customer_segment`", color_name="Segment",
    title="Revenue mix — Homeowner / Contractor / Commercial"
), 0, 17, 3, 5))

PAGE_EXEC.append(at(bar(DS_INV,
    x=("`product_line`", "Product Line"),
    y=("SUM(`estimated_gross_margin_usd`)", "Gross Margin USD"),
    color=("`product_tier`", "Tier"),
    title="Gross Margin by Product Line × Tier",
    stacking="normal",
), 3, 17, 3, 5))


# ============== PAGE 2: Sales Performance ==============
PAGE_SALES: list[dict] = []

PAGE_SALES.append(at(text(
    "## Sales Performance\n"
    "**Audience:** sales leaders & regional managers.  "
    "**What you can do:** drill into top customers, watch pipeline conversion, "
    "find at-risk accounts (open pipeline but no recent invoice), monitor discount discipline.  \n"
    "RLS scopes regional managers to their territory automatically — they see fewer rows but the same charts."
), 0, 0, 6, 2))

PAGE_SALES.append(at(filter_widget("filter-date-range-picker", "Invoice date",
                                  "invoice_date", [DS_INV]),                       0, 2, 2, 2))
PAGE_SALES.append(at(filter_widget("filter-multi-select", "Territory",
                                  "territory", [DS_INV, DS_C360, DS_CRM]),         2, 2, 1, 2))
PAGE_SALES.append(at(filter_widget("filter-multi-select", "Segment",
                                  "customer_segment", [DS_INV, DS_C360]),          3, 2, 1, 2))
PAGE_SALES.append(at(filter_widget("filter-multi-select", "Product Line",
                                  "product_line", [DS_INV]),                       4, 2, 1, 2))
PAGE_SALES.append(at(filter_widget("filter-multi-select", "Lead Source",
                                  "lead_source", [DS_CRM]),                        5, 2, 1, 2))

PAGE_SALES.append(at(counter(DS_INV, "COUNT(DISTINCT `invoice_id`)", "Invoices"),                     0, 4, 1, 3))
PAGE_SALES.append(at(counter(DS_INV, "AVG(`net_invoice_amount`)",   "Avg Line Value"),                1, 4, 1, 3))
PAGE_SALES.append(at(counter(DS_INV, "SUM(-`discount_amount`) / NULLIF(SUM(`gross_line_amount`),0)",
                             "Discount %"),                                                            2, 4, 1, 3))
PAGE_SALES.append(at(counter(DS_CRM, "COUNT(DISTINCT `deal_id`)", "Deals"),                            3, 4, 1, 3))
PAGE_SALES.append(at(counter(DS_CRM, "SUM(CASE WHEN `deal_outcome`='WON' THEN 1 ELSE 0 END) / NULLIF(SUM(CASE WHEN `deal_outcome` IN ('WON','LOST') THEN 1 ELSE 0 END),0)",
                             "Win Rate"),                                                              4, 4, 1, 3))
PAGE_SALES.append(at(counter(DS_INV, "COUNT(DISTINCT `product_key`)", "Distinct Products Sold"),       5, 4, 1, 3))

# Trends
PAGE_SALES.append(at(line(DS_INV,
    x=("`invoice_month`", "Month"),
    y=("SUM(`net_invoice_amount`)", "Net Revenue"),
    color=("`territory`", "Territory"),
    title="Monthly Net Revenue by Territory"
), 0, 7, 4, 5))

PAGE_SALES.append(at(pie(DS_CRM,
    angle_expr="COUNT(*)", angle_name="Deals",
    color_expr="`deal_outcome`", color_name="Outcome",
    title="Deals by outcome (CRM funnel)"
), 4, 7, 2, 5))

# Customer leaderboard + pipeline
PAGE_SALES.append(at(bar(DS_INV,
    x=("`customer_name`", "Customer"),
    y=("SUM(`net_invoice_amount`)", "Net Revenue"),
    title="Top 15 customers (filtered)"
), 0, 12, 6, 5))

PAGE_SALES.append(at(bar(DS_CRM,
    x=("`deal_stage`", "Stage"),
    y=("SUM(`amount_usd`)", "Pipeline USD"),
    title="Open + Closed pipeline by stage",
    sort="natural-order",
), 0, 17, 3, 5))

PAGE_SALES.append(at(line(DS_INV,
    x=("`invoice_month`", "Month"),
    y=("SUM(-`discount_amount`) / NULLIF(SUM(`gross_line_amount`),0)", "Discount %"),
    color=None,
    title="Discount % over time"
), 3, 17, 3, 5))


# ============== PAGE 3: Finance & GL Deep-Dive ==============
PAGE_FIN: list[dict] = []

PAGE_FIN.append(at(text(
    "## Finance & GL — the 1 GB Power BI cap killer\n"
    "**Audience:** Finance team, controllers.  "
    "**What this proves:** 600,000+ GL rows over 5 years, served live by a serverless SQL warehouse "
    "in under a second per visualization.  \n"
    "In Power BI Pro, this multi-year GL semantic model would not load. "
    "Here it cross-filters in real time — click any year, BU, or category to drill in."
), 0, 0, 6, 2))

PAGE_FIN.append(at(filter_widget("filter-date-range-picker", "GL date",
                                "transaction_date", [DS_GL]),               0, 2, 2, 2))
PAGE_FIN.append(at(filter_widget("filter-multi-select", "Year",
                                "gl_year", [DS_GL]),                         2, 2, 1, 2))
PAGE_FIN.append(at(filter_widget("filter-multi-select", "GL Category",
                                "gl_category", [DS_GL]),                     3, 2, 1, 2))
PAGE_FIN.append(at(filter_widget("filter-multi-select", "Business Unit",
                                "business_unit", [DS_GL]),                   4, 2, 1, 2))
PAGE_FIN.append(at(filter_widget("filter-multi-select", "Territory",
                                "territory", [DS_GL, DS_AR]),                5, 2, 1, 2))

# Counters
PAGE_FIN.append(at(counter(DS_GL, "SUM(CASE WHEN `gl_category`='REVENUE' THEN -`amount_usd_raw` ELSE 0 END)",
                          "Revenue (5y)"),                                                  0, 4, 1, 3))
PAGE_FIN.append(at(counter(DS_GL, "SUM(CASE WHEN `gl_category`='COGS'    THEN  `amount_usd_raw` ELSE 0 END)",
                          "COGS (5y)"),                                                     1, 4, 1, 3))
PAGE_FIN.append(at(counter(DS_GL, "SUM(CASE WHEN `gl_category`='OPEX'    THEN  `amount_usd_raw` ELSE 0 END)",
                          "OpEx (5y)"),                                                     2, 4, 1, 3))
PAGE_FIN.append(at(counter(DS_GL, "SUM(CASE WHEN `gl_category`='CAPEX'   THEN  `amount_usd_raw` ELSE 0 END)",
                          "CapEx (5y)"),                                                    3, 4, 1, 3))
PAGE_FIN.append(at(counter(DS_AR, "SUM(`outstanding_usd`)",                "AR Outstanding"), 4, 4, 1, 3))
PAGE_FIN.append(at(counter(DS_GL, "COUNT(*)",                              "GL Rows"),       5, 4, 1, 3))

# Multi-year stacked area
PAGE_FIN.append(at(area(DS_GL,
    x=("`gl_month`", "Month"),
    y=("SUM(`amount_usd_signed`)", "Amount (USD)"),
    color=("`gl_category`", "GL Category"),
    title="Monthly GL trend across 5 years (revenue / COGS / OpEx / CapEx)"
), 0, 7, 6, 5))

# Year over year revenue
PAGE_FIN.append(at(bar(DS_GL,
    x=("`gl_year`", "Year"),
    y=("SUM(CASE WHEN `gl_category`='REVENUE' THEN -`amount_usd_raw` ELSE 0 END)", "Revenue"),
    title="Annual revenue (signed-flipped)",
    sort="x",
), 0, 12, 3, 5))

PAGE_FIN.append(at(bar(DS_GL,
    x=("`business_unit`", "Business Unit"),
    y=("SUM(`amount_usd_signed`)", "Spend"),
    color=("`gl_category`", "Category"),
    title="GL by Business Unit × Category",
    stacking="normal",
), 3, 12, 3, 5))

# AR aging stacked by territory
PAGE_FIN.append(at(bar(DS_AR,
    x=("`aging_bucket`", "Aging Bucket"),
    y=("SUM(`outstanding_usd`)", "Outstanding (USD)"),
    color=("`territory`", "Territory"),
    title="AR Aging by territory",
    sort="natural-order",
    stacking="normal",
), 0, 17, 4, 5))

PAGE_FIN.append(at(table(DS_GL, [
    ("`gl_account`",      "Account",     "string", "string"),
    ("`gl_description`",  "Description", "string", "string"),
    ("`gl_category`",     "Category",    "string", "string"),
    ("SUM(`amount_usd_signed`)", "Net amount (USD)", "float", "number"),
], "GL line items (drill-down)"), 4, 17, 2, 5))


# ============== PAGE 4: Marketing & Web ==============
PAGE_MKT: list[dict] = []

PAGE_MKT.append(at(text(
    "## Marketing & Web\n"
    "**Audience:** Marketing, GTM teams.  "
    "**What you can do:** see traffic by source/medium, find the campaigns that produce quote requests, "
    "compare device mix and territories.  \n"
    "Filter by campaign or source to instantly slice every chart on the page — including the funnel."
), 0, 0, 6, 2))

PAGE_MKT.append(at(filter_widget("filter-date-range-picker", "Session date",
                                "session_date", [DS_WEB]),         0, 2, 2, 2))
PAGE_MKT.append(at(filter_widget("filter-multi-select", "Source",
                                "traffic_source", [DS_WEB]),        2, 2, 1, 2))
PAGE_MKT.append(at(filter_widget("filter-multi-select", "Medium",
                                "traffic_medium", [DS_WEB]),        3, 2, 1, 2))
PAGE_MKT.append(at(filter_widget("filter-multi-select", "Campaign",
                                "campaign", [DS_WEB]),              4, 2, 1, 2))
PAGE_MKT.append(at(filter_widget("filter-multi-select", "Country",
                                "country", [DS_WEB]),               5, 2, 1, 2))

PAGE_MKT.append(at(counter(DS_WEB, "COUNT(DISTINCT `session_id`)",         "Sessions"),                 0, 4, 1, 3))
PAGE_MKT.append(at(counter(DS_WEB, "COUNT(DISTINCT `user_pseudo_id`)",     "Visitors"),                 1, 4, 1, 3))
PAGE_MKT.append(at(counter(DS_WEB, "SUM(CASE WHEN `is_lead_event` THEN 1 ELSE 0 END)", "Lead Events"),  2, 4, 1, 3))
PAGE_MKT.append(at(counter(DS_WEB, "SUM(CASE WHEN `event_name`='request_quote' THEN 1 ELSE 0 END)",
                           "Quote Requests"),                                                            3, 4, 1, 3))
PAGE_MKT.append(at(counter(DS_WEB, "SUM(CASE WHEN `is_lead_event` THEN 1 ELSE 0 END) / NULLIF(COUNT(*),0)",
                           "Lead Conversion %"),                                                         4, 4, 1, 3))
PAGE_MKT.append(at(counter(DS_WEB, "COUNT(DISTINCT `campaign`)",          "Active Campaigns"),           5, 4, 1, 3))

PAGE_MKT.append(at(area(DS_WEB,
    x=("`session_month`", "Month"),
    y=("COUNT(DISTINCT `session_id`)", "Sessions"),
    color=("`traffic_source`", "Source"),
    title="Sessions by source over time"
), 0, 7, 4, 5))

PAGE_MKT.append(at(pie(DS_WEB,
    angle_expr="COUNT(*)",                       angle_name="Events",
    color_expr="`device_category`",              color_name="Device",
    title="Device mix"
), 4, 7, 2, 5))

PAGE_MKT.append(at(bar(DS_WEB,
    x=("`campaign`", "Campaign"),
    y=("SUM(CASE WHEN `event_name`='request_quote' THEN 1 ELSE 0 END)", "Quote Requests"),
    title="Top campaigns by quote-request volume",
), 0, 12, 3, 5))

PAGE_MKT.append(at(bar(DS_WEB,
    x=("`event_name`", "Event"),
    y=("COUNT(*)", "Events"),
    title="Funnel: page_view → add_to_inspiration → contact_form → request_quote → find_dealer",
    sort="y-reversed",
), 3, 12, 3, 5))

PAGE_MKT.append(at(bar(DS_WEB,
    x=("`country`", "Country"),
    y=("COUNT(DISTINCT `session_id`)", "Sessions"),
    color=("`territory`", "Territory"),
    title="Geographic distribution",
    stacking="normal",
), 0, 17, 6, 5))


# ============== PAGE 5: Customer 360 ==============
PAGE_CUST: list[dict] = []

PAGE_CUST.append(at(text(
    "## Customer 360\n"
    "**Audience:** Account managers.  "
    "**Per-customer story:** lifetime revenue, days since last invoice, open CRM pipeline, "
    "credit limit, AR exposure.  \n"
    "**Tip:** click any segment / territory in the charts and the table re-scopes — "
    "useful for finding 'whales without recent activity' or 'at-risk contractors'."
), 0, 0, 6, 2))

PAGE_CUST.append(at(filter_widget("filter-multi-select", "Territory",
                                 "territory", [DS_C360, DS_AR]),                 0, 2, 2, 2))
PAGE_CUST.append(at(filter_widget("filter-multi-select", "Segment",
                                 "customer_segment", [DS_C360, DS_AR]),          2, 2, 2, 2))
PAGE_CUST.append(at(filter_widget("filter-multi-select", "Country",
                                 "country", [DS_C360, DS_AR]),                   4, 2, 2, 2))

PAGE_CUST.append(at(counter(DS_C360, "COUNT(*)",                   "Total Customers"),     0, 4, 1, 3))
PAGE_CUST.append(at(counter(DS_C360, "SUM(CASE WHEN `is_active` THEN 1 ELSE 0 END)",
                            "Active Customers"),                                            1, 4, 1, 3))
PAGE_CUST.append(at(counter(DS_C360, "SUM(CASE WHEN `days_since_last_invoice` > 90 OR `last_invoice_date` IS NULL THEN 1 ELSE 0 END)",
                            "At-Risk (90d+ no invoice)"),                                   2, 4, 1, 3))
PAGE_CUST.append(at(counter(DS_C360, "SUM(`open_pipeline_usd`)",   "Open Pipeline"),        3, 4, 1, 3))
PAGE_CUST.append(at(counter(DS_C360, "SUM(`credit_limit_usd`)",    "Total Credit Limit"),   4, 4, 1, 3))
PAGE_CUST.append(at(counter(DS_C360, "AVG(`lifetime_revenue_usd`)", "Avg LTV"),             5, 4, 1, 3))

PAGE_CUST.append(at(bar(DS_C360,
    x=("`customer_segment`", "Segment"),
    y=("SUM(`lifetime_revenue_usd`)", "Lifetime Revenue"),
    color=("`territory`", "Territory"),
    title="Lifetime revenue by segment × territory",
    stacking="normal",
), 0, 7, 3, 5))

PAGE_CUST.append(at(bar(DS_C360,
    x=("`customer_segment`", "Segment"),
    y=("SUM(`open_pipeline_usd`)", "Open Pipeline"),
    title="Open pipeline by segment",
), 3, 7, 3, 5))

PAGE_CUST.append(at(bar(DS_AR,
    x=("`aging_bucket`", "Aging Bucket"),
    y=("SUM(`outstanding_usd`)", "Outstanding"),
    color=("`customer_segment`", "Segment"),
    title="AR aging by segment",
    sort="natural-order",
    stacking="normal",
), 0, 12, 6, 5))

PAGE_CUST.append(at(table(DS_C360, [
    ("`customer_name`",          "Customer",              "string", "string"),
    ("`customer_segment`",       "Segment",               "string", "string"),
    ("`territory`",              "Territory",             "string", "string"),
    ("`country`",                "Country",               "string", "string"),
    ("`lifetime_revenue_usd`",   "Lifetime Revenue",      "float",  "number"),
    ("`lifetime_invoices`",      "Invoices",              "integer","number"),
    ("`open_pipeline_usd`",      "Open Pipeline",         "float",  "number"),
    ("`credit_limit_usd`",       "Credit Limit",          "float",  "number"),
    ("`days_since_last_invoice`","Days Since Last Inv.",  "integer","number"),
], "Customer detail (filtered, sorted by Lifetime Revenue)"), 0, 17, 6, 6))


# ───────────────────────── assemble ───────────────────────────────
DASHBOARD = {
    "datasets": list(DATASETS.values()),
    "pages": [
        page("p_exec",  "Executive Overview",     PAGE_EXEC),
        page("p_sales", "Sales Performance",      PAGE_SALES),
        page("p_fin",   "Finance & GL Deep-Dive", PAGE_FIN),
        page("p_mkt",   "Marketing & Web",        PAGE_MKT),
        page("p_cust",  "Customer 360",           PAGE_CUST),
    ],
    "uiSettings": {"theme": {"widgetHeaderAlignment": "ALIGNMENT_UNSPECIFIED"}},
}


# ───────────────────────── deploy ─────────────────────────────────

def main():
    name = os.environ.get("DASHBOARD_NAME", "Techo-Bloc — Sales & Finance 360 (Lakehouse Demo)")
    cleaned = strip_nulls(DASHBOARD)
    payload = {
        "display_name": name,
        "warehouse_id": WAREHOUSE,
        "serialized_dashboard": json.dumps(cleaned),
    }

    existing = sys.argv[1] if len(sys.argv) > 1 else None
    if existing:
        endpoint, method = f"/api/2.0/lakeview/dashboards/{existing}", "patch"
    else:
        payload["parent_path"] = PARENT_PATH
        endpoint, method = "/api/2.0/lakeview/dashboards", "post"

    res = subprocess.run(
        ["databricks", "api", method, endpoint, f"--profile={PROFILE}",
         f"--json={json.dumps(payload)}"],
        capture_output=True, text=True
    )
    if res.returncode != 0:
        print("STDERR:", res.stderr); print("STDOUT:", res.stdout); sys.exit(2)
    out = json.loads(res.stdout)
    dashboard_id = out.get("dashboard_id") or existing
    print(json.dumps({
        "dashboard_id": dashboard_id,
        "display_name": out.get("display_name"),
        "method": method,
        "pages": [p["displayName"] for p in DASHBOARD["pages"]],
        "datasets": list(DATASETS.keys()),
        "widget_count": sum(len(p["layout"]) for p in DASHBOARD["pages"]),
    }, indent=2))

    pub = subprocess.run(
        ["databricks", "api", "post",
         f"/api/2.0/lakeview/dashboards/{dashboard_id}/published",
         f"--profile={PROFILE}",
         f"--json={json.dumps({'warehouse_id': WAREHOUSE, 'embed_credentials': True})}"],
        capture_output=True, text=True
    )
    print("publish:", pub.returncode, (pub.stdout or pub.stderr)[:200])


if __name__ == "__main__":
    main()
