#!/usr/bin/env python3
"""Build the Techo-Bloc AI/BI dashboard and create it in Dazana-classic-ws."""
import json
import subprocess
import uuid

PROFILE = "Dazana-classic-ws-pat"
WAREHOUSE = "a82088b3bfe8752c"
PARENT_PATH = "/Users/dazana.hasan@databricks.com"
CATALOG = "dazana_classic_ws_catalog"

DBR = "#FFAB00"; GRN = "#00A972"; RED = "#FF3621"; BLU = "#8BCAE7"; PNK = "#FCA4A1"
PALETTE = [DBR, GRN, RED, BLU, "#AB4057", "#99DDB4", PNK, "#919191"]


def nid() -> str:
    return uuid.uuid4().hex[:8]


def make_dataset(name: str, display: str, sql: str) -> dict:
    return {"name": name, "displayName": display, "queryLines": [sql]}


def counter(ds: str, expr: str, name: str) -> dict:
    # Match the proven Lakeview shape: disaggregated=true, no `format` key,
    # field name mirrors the expression style.
    field_name = expr.lower().replace(" ", "").replace("`", "")
    return {
        "widget": {
            "name": nid(),
            "queries": [{
                "name": "main_query",
                "query": {
                    "datasetName": ds,
                    "fields": [{"name": field_name, "expression": expr}],
                    "disaggregated": True,
                },
            }],
            "spec": {
                "version": 2,
                "widgetType": "counter",
                "encodings": {"value": {
                    "fieldName": field_name,
                    "displayName": name,
                }},
                "frame": {"showTitle": True, "title": name},
            },
        }
    }


def _safe_name(expr: str) -> str:
    """Mirror Lakeview's field-name convention: lowercase, no spaces, no backticks."""
    return expr.lower().replace(" ", "").replace("`", "").replace('"', "")


def bar(ds: str, x: tuple, y: tuple, title: str, sort: str = "y-reversed",
        color: tuple | None = None, horizontal: bool = False) -> dict:
    xn, yn = _safe_name(x[0]), _safe_name(y[0])
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
        cn = _safe_name(color[0])
        fields.append({"name": cn, "expression": color[0]})
        encodings["color"] = {"fieldName": cn, "scale": {"type": "categorical"}, "displayName": color[1]}
    spec = {
        "version": 3,
        "widgetType": "bar",
        "encodings": encodings,
        "frame": {"showTitle": True, "title": title},
    }
    if horizontal:
        spec["encodings"]["x"], spec["encodings"]["y"] = spec["encodings"]["y"], spec["encodings"]["x"]
    return {
        "widget": {
            "name": nid(),
            "queries": [{"name": "main_query", "query": {"datasetName": ds, "fields": fields, "disaggregated": False}}],
            "spec": spec,
        }
    }


def line(ds: str, x: tuple, y: tuple, color: tuple, title: str) -> dict:
    xn, yn, cn = _safe_name(x[0]), _safe_name(y[0]), _safe_name(color[0])
    return {
        "widget": {
            "name": nid(),
            "queries": [{
                "name": "main_query",
                "query": {
                    "datasetName": ds,
                    "fields": [
                        {"name": xn, "expression": x[0]},
                        {"name": yn, "expression": y[0]},
                        {"name": cn, "expression": color[0]},
                    ],
                    "disaggregated": False,
                },
            }],
            "spec": {
                "version": 3,
                "widgetType": "line",
                "encodings": {
                    "x": {"fieldName": xn, "scale": {"type": "temporal"}, "displayName": x[1]},
                    "y": {"fieldName": yn, "scale": {"type": "quantitative"}, "displayName": y[1]},
                    "color": {"fieldName": cn, "scale": {"type": "categorical"}, "displayName": color[1]},
                },
                "frame": {"showTitle": True, "title": title},
            },
        }
    }


def area(ds: str, x: tuple, y: tuple, color: tuple, title: str) -> dict:
    w = line(ds, x, y, color, title)
    w["widget"]["spec"]["widgetType"] = "area"
    return w


def pie(ds: str, angle_expr: str, angle_name: str, color_expr: str, color_name: str, title: str) -> dict:
    an, cn = _safe_name(angle_expr), _safe_name(color_expr)
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
    fields = []
    cols = []
    used = set()
    for (expr, name, ctype, display_as) in columns:
        fname = _safe_name(expr)
        # Ensure unique field names
        base = fname
        i = 1
        while fname in used:
            fname = f"{base}_{i}"
            i += 1
        used.add(fname)
        fields.append({"name": fname, "expression": expr})
        col = {"fieldName": fname, "type": ctype, "displayAs": display_as, "title": name, "displayName": name}
        if display_as == "number":
            col["numberFormat"] = "#,##0.00"
            col["alignContent"] = "right"
        cols.append(col)
    return {
        "widget": {
            "name": nid(),
            "queries": [{"name": "main_query", "query": {"datasetName": ds, "fields": fields, "disaggregated": True}}],
            "spec": {
                "version": 1,
                "widgetType": "table",
                "encodings": {"columns": cols},
                "frame": {"showTitle": True, "title": title},
            },
        }
    }


def md(text: str) -> dict:
    """Markdown/text widget — uses Lakeview's text-block schema (widgetType: text)."""
    return {
        "widget": {
            "name": nid(),
            "spec": {
                "version": 1,
                "widgetType": "text",
                "frame": {"showTitle": False},
                "text": text,
            },
        }
    }


def at(widget: dict, x: int, y: int, w: int, h: int) -> dict:
    return {**widget, "position": {"x": x, "y": y, "width": w, "height": h}}


# ---------------- Datasets ----------------
DATASETS = []
def add_ds(name, display, sql):
    DATASETS.append(make_dataset(name, display, sql))
    return name

DS_KPI = add_ds("kpis", "Headline KPIs", f"""
SELECT
  SUM(net_invoice_amount) AS net_revenue,
  SUM(gross_line_amount)  AS gross_revenue,
  SUM(quantity)           AS units_sold,
  COUNT(DISTINCT invoice_id) AS invoice_count,
  COUNT(DISTINCT customer_key) AS active_customers
FROM {CATALOG}.techo_bloc_silver.fact_invoice_lines
""")

DS_OPEN = add_ds("open_pipeline", "Open Pipeline (CRM)", f"""
SELECT SUM(amount_usd) AS open_pipeline_usd
FROM {CATALOG}.techo_bloc_silver.fact_crm_deals
WHERE deal_outcome = 'OPEN'
""")

DS_GL = add_ds("gl_monthly", "Multi-year GL trend (5+ years)", f"""
SELECT
  date_trunc('MONTH', transaction_date)         AS gl_month,
  gl_category,
  SUM(CASE WHEN gl_category='REVENUE' THEN -amount_usd ELSE amount_usd END) AS amount_usd
FROM {CATALOG}.techo_bloc_silver.fact_gl_transactions
GROUP BY 1,2
""")

DS_PRODLINE = add_ds("rev_by_prodline", "Net Revenue by Product Line", f"""
SELECT p.product_line, ROUND(SUM(f.net_invoice_amount),2) AS net_revenue
FROM {CATALOG}.techo_bloc_silver.fact_invoice_lines f
JOIN {CATALOG}.techo_bloc_silver.dim_product p ON f.product_key = p.product_key
GROUP BY 1
""")

DS_TERRITORY = add_ds("rev_by_territory", "Net Revenue by Territory", f"""
SELECT c.territory, ROUND(SUM(f.net_invoice_amount),2) AS net_revenue
FROM {CATALOG}.techo_bloc_silver.fact_invoice_lines f
JOIN {CATALOG}.techo_bloc_silver.dim_customer c ON f.customer_key = c.customer_key
GROUP BY 1
""")

DS_SEGMENT = add_ds("rev_by_segment", "Revenue by Customer Segment", f"""
SELECT c.customer_segment,
       ROUND(SUM(f.net_invoice_amount),2) AS net_revenue,
       COUNT(DISTINCT c.customer_key)     AS customers
FROM {CATALOG}.techo_bloc_silver.fact_invoice_lines f
JOIN {CATALOG}.techo_bloc_silver.dim_customer c ON f.customer_key = c.customer_key
GROUP BY 1
""")

DS_SOURCE = add_ds("source_split", "D365 vs AX 2012 split", f"""
SELECT source_system, ROUND(SUM(net_invoice_amount),2) AS net_revenue, COUNT(DISTINCT invoice_id) AS invoice_count
FROM {CATALOG}.techo_bloc_silver.fact_invoice_lines
GROUP BY 1
""")

DS_AR = add_ds("ar_aging", "AR Aging Buckets", f"""
SELECT aging_bucket, ROUND(SUM(outstanding_usd),2) AS outstanding_usd
FROM {CATALOG}.techo_bloc_gold.vw_ar_aging
GROUP BY 1
""")

DS_TOPCUST = add_ds("top_customers", "Top 15 customers by lifetime revenue", f"""
SELECT customer_name, customer_segment, territory,
       ROUND(lifetime_revenue_usd,2) AS lifetime_revenue_usd,
       lifetime_invoices,
       ROUND(open_pipeline_usd,2)    AS open_pipeline_usd
FROM {CATALOG}.techo_bloc_gold.vw_customer_360
ORDER BY lifetime_revenue_usd DESC
LIMIT 15
""")

DS_WEBLEAD = add_ds("web_leads", "Web sessions vs lead events", f"""
SELECT date_trunc('MONTH', session_date) AS month,
       SUM(CASE WHEN is_lead_event THEN 1 ELSE 0 END) AS lead_events,
       COUNT(*)                                       AS total_sessions
FROM {CATALOG}.techo_bloc_silver.fact_web_engagement
GROUP BY 1
""")

DS_CAMPAIGN = add_ds("campaign_funnel", "Campaign funnel", f"""
SELECT campaign,
       SUM(CASE WHEN event_name = 'page_view'         THEN 1 ELSE 0 END) AS page_views,
       SUM(CASE WHEN event_name = 'add_to_inspiration' THEN 1 ELSE 0 END) AS adds,
       SUM(CASE WHEN event_name = 'request_quote'     THEN 1 ELSE 0 END) AS quotes
FROM {CATALOG}.techo_bloc_silver.fact_web_engagement
GROUP BY 1
""")

DS_PROD_TIER = add_ds("rev_prod_tier", "Net Rev by Product Line × Tier", f"""
SELECT p.product_line, p.product_tier, ROUND(SUM(f.net_invoice_amount),2) AS net_revenue
FROM {CATALOG}.techo_bloc_silver.fact_invoice_lines f
JOIN {CATALOG}.techo_bloc_silver.dim_product p ON f.product_key = p.product_key
GROUP BY 1,2
""")

# ---------------- Pages / Layout ----------------
LAYOUT = []

# Row 1: KPI counters (top of canvas)
LAYOUT.append(at(counter(DS_KPI, "SUM(`net_revenue`)", "Net Revenue (USD)"),         0, 0, 1, 3))
LAYOUT.append(at(counter(DS_KPI, "SUM(`gross_revenue`)", "Gross Revenue (USD)"),     1, 0, 1, 3))
LAYOUT.append(at(counter(DS_KPI, "SUM(`active_customers`)", "Active Customers"),     2, 0, 1, 3))
LAYOUT.append(at(counter(DS_KPI, "SUM(`invoice_count`)", "Invoice Count"),           3, 0, 1, 3))
LAYOUT.append(at(counter(DS_OPEN, "SUM(`open_pipeline_usd`)", "Open Pipeline (USD)"), 4, 0, 2, 3))

# Row 2: GL Multi-year trend (1GB Power BI cap killer)
LAYOUT.append(at(area(DS_GL,
    x=("`gl_month`", "Month"),
    y=("SUM(`amount_usd`)", "USD"),
    color=("`gl_category`", "GL Category"),
    title="Multi-year GL trend (5+ years, 600K rows)"
), 0, 3, 6, 5))

# Row 3: Revenue by product line + territory + segment
LAYOUT.append(at(bar(DS_PRODLINE,
    x=("`product_line`", "Product Line"),
    y=("SUM(`net_revenue`)", "Net Revenue"),
    title="Net Revenue by Product Line",
), 0, 8, 3, 5))

LAYOUT.append(at(bar(DS_TERRITORY,
    x=("`territory`", "Territory"),
    y=("SUM(`net_revenue`)", "Net Revenue"),
    title="Net Revenue by Territory (RLS demo target)",
    sort="y-reversed",
), 3, 8, 3, 5))

LAYOUT.append(at(pie(DS_SEGMENT,
    angle_expr="SUM(`net_revenue`)", angle_name="Net Revenue",
    color_expr="`customer_segment`", color_name="Segment",
    title="Revenue by Customer Segment"
), 0, 13, 3, 5))

LAYOUT.append(at(bar(DS_AR,
    x=("`aging_bucket`", "Aging Bucket"),
    y=("SUM(`outstanding_usd`)", "Outstanding (USD)"),
    title="AR Aging (multi-year, D365 + AX 2012)",
    sort="natural-order",
), 3, 13, 3, 5))

# Row 4: D365 vs AX split + Top customers table
LAYOUT.append(at(pie(DS_SOURCE,
    angle_expr="SUM(`net_revenue`)", angle_name="Net Revenue",
    color_expr="`source_system`", color_name="Source System",
    title="D365 vs AX 2012 net revenue split"
), 0, 18, 2, 5))

LAYOUT.append(at(bar(DS_PROD_TIER,
    x=("`product_line`", "Product Line"),
    y=("SUM(`net_revenue`)", "Net Revenue"),
    color=("`product_tier`", "Tier"),
    title="Product Line by Product Tier",
), 2, 18, 4, 5))

LAYOUT.append(at(table(DS_TOPCUST, [
    ("`customer_name`",         "Customer",            "string", "string"),
    ("`customer_segment`",      "Segment",             "string", "string"),
    ("`territory`",             "Territory",           "string", "string"),
    ("`lifetime_revenue_usd`",  "Lifetime Revenue",    "float",  "number"),
    ("`lifetime_invoices`",     "Invoices",            "integer","number"),
    ("`open_pipeline_usd`",     "Open Pipeline",       "float",  "number"),
], "Top 15 customers (lifetime)"), 0, 23, 6, 6))

# Row 5: Web -> leads
LAYOUT.append(at(line(DS_WEBLEAD,
    x=("`month`", "Month"),
    y=("SUM(`total_sessions`)", "Total sessions"),
    color=("'Sessions'", "Series"),
    title="Web sessions per month (GA)"
), 0, 29, 3, 5))

LAYOUT.append(at(bar(DS_CAMPAIGN,
    x=("`campaign`", "Campaign"),
    y=("SUM(`quotes`)", "Quote requests"),
    title="Campaign to quote-request volume",
), 3, 29, 3, 5))

PAGE = {
    "name": nid(),
    "displayName": "Techo-Bloc 360",
    "pageType": "PAGE_TYPE_CANVAS",
    "layout": LAYOUT,
}

DASHBOARD = {
    "datasets": DATASETS,
    "pages": [PAGE],
    "uiSettings": {"theme": {"widgetHeaderAlignment": "ALIGNMENT_UNSPECIFIED"}},
}


def strip_nulls(obj):
    if isinstance(obj, dict):
        return {k: strip_nulls(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [strip_nulls(v) for v in obj]
    return obj


def main():
    import sys
    cleaned = strip_nulls(DASHBOARD)
    import os
    name = os.environ.get("DASHBOARD_NAME", "Techo-Bloc — Sales & Finance 360 (Lakehouse Demo)")
    payload = {
        "display_name": name,
        "warehouse_id": WAREHOUSE,
        "serialized_dashboard": json.dumps(cleaned),
    }
    # PATCH if existing id is given, else POST
    existing_id = sys.argv[1] if len(sys.argv) > 1 else None
    if existing_id:
        endpoint = f"/api/2.0/lakeview/dashboards/{existing_id}"
        method = "patch"
    else:
        payload["parent_path"] = PARENT_PATH
        endpoint = "/api/2.0/lakeview/dashboards"
        method = "post"

    res = subprocess.run(
        ["databricks", "api", method, endpoint,
         f"--profile={PROFILE}", f"--json={json.dumps(payload)}"],
        capture_output=True, text=True
    )
    if res.returncode != 0:
        print("STDERR:", res.stderr)
        print("STDOUT:", res.stdout)
        raise SystemExit(2)
    out = json.loads(res.stdout)
    dashboard_id = out.get("dashboard_id") or existing_id
    print(json.dumps({
        "dashboard_id": dashboard_id,
        "display_name": out.get("display_name"),
        "path": out.get("path"),
        "method": method,
    }, indent=2))

    # Republish so the live URL gets the new layout
    pub = subprocess.run(
        ["databricks", "api", "post", f"/api/2.0/lakeview/dashboards/{dashboard_id}/published",
         f"--profile={PROFILE}",
         f"--json={json.dumps({'warehouse_id': WAREHOUSE, 'embed_credentials': True})}"],
        capture_output=True, text=True
    )
    print("publish:", pub.returncode, pub.stdout[:200] if pub.stdout else pub.stderr[:200])


if __name__ == "__main__":
    main()
