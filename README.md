# Techo-Bloc — Databricks AI/BI Demo

A complete, end-to-end Databricks demo built for **Techo-Bloc**, a North-American hardscape manufacturer (pavers, slabs, retaining walls, fire pits) running through an ERP modernization from **AX 2012 → Dynamics 365 F&O**. The demo answers the three questions their leadership is weighing:

1. **Cost** — can Databricks be predictable and cheaper than Microsoft Fabric for our workload?
2. **Governance** — can it solve our column-level lineage, masking, and RLS gaps?
3. **AI / BI** — can it bypass the Power BI Pro 1 GB cap with sub-second query and natural-language analytics?

Every artifact here is built from synthetic data and runs on a single Unity-Catalog-enabled Databricks workspace.

---

## What's in the demo

```
                ┌──── Bronze (raw landed) ─────┐  ┌──── Silver (Kimball) ───┐  ┌──── Gold (BI ready) ─────┐
D365 F&O ──────►│ d365_custinvoicetrans        │  │ dim_customer            │  │ vw_dim_customer  (masks)  │
(Synapse Link)  │ d365_markuptrans  ★          │  │ dim_product             │  │ vw_dim_employee  (masks)  │
                │ d365_custtable    (PII)      │  │ dim_employee  (PII)     │  │ mv_sales_summary (MV)     │
                │ d365_inventtable             │  │ dim_region              │  │ vw_finance_kpis           │
                │ d365_dimensionvalues         │  │ dim_date                │  │ vw_customer_360           │
AX 2012  ──────►│ ax2012_custinvoicejour       │  │ fact_invoice_lines  ★   │  │ vw_ar_aging               │
(historical)    │ ax2012_gl_transactions (5y)  │  │ fact_gl_transactions    │  │ metrics_techo_bloc (YAML) │
UKG  ──────────►│ ukg_employees     (PII)      │  │ fact_web_engagement     │  └──────────────────────────┘
HubSpot ──────►│ hubspot_deals                 │  │ fact_crm_deals          │
GA  ───────────►│ ga_sessions                  │  └─────────────────────────┘
                └──────────────────────────────┘                                      │
                                                                                       ▼
                                                              ┌────────────────────────────────────┐
                                                              │  AI/BI Dashboard  +  Genie space   │
                                                              │  +  Unity Catalog column masks/RLS │
                                                              └────────────────────────────────────┘

★ = entity-resolution interdependency story (MarkupTrans → CustInvoiceTrans, AX → D365 unification)
```

| Demo asset | What it proves |
|---|---|
| 10 **bronze** tables with realistic D365 / AX 2012 / UKG / HubSpot / GA shapes | Synapse-Link-style raw landing zone |
| 9 **silver** Kimball dims/facts | Cleaning, dedup, **D365 + AX 2012 unification**, MarkupTrans applied |
| 4 **gold** views + 1 **materialized view** + 1 **metric view** | Business-ready BI, KPI consistency across tools |
| **Column masks** on email / phone / address / SSN / salary | PII enforced at Unity Catalog, not the BI tool |
| **Row-level security** on `dim_customer` and `fact_gl_transactions` | Regional manager only sees their territory automatically |
| **Live persona override** table | Flip between HR / Finance / Sales Rep / Regional Mgr / Leadership in one UPDATE |
| **Lakeview AI/BI dashboard** with 16 widgets | Multi-year GL, customer 360, AR aging, source-system unification |
| **Genie space** with 13 sample questions, 16 instructions, 12 benchmarks | Natural-language analytics over the metric view |

The headline numbers from a clean deploy: ~108K invoice lines (D365 + AX combined), ~600K GL rows over 5 years, $766M lifetime net revenue, 4,800 customers across 4 territories, 12 KPIs in the metric view.

---

## Repo layout

```
.
├── 01_setup_catalog.sql                     # schemas
├── 02_bronze_d365.sql                       # D365 F&O bronze tables
├── 03_bronze_legacy_and_other_sources.sql   # AX 2012, UKG, HubSpot, GA
├── 04_silver.sql                            # cleaned/integrated Kimball dims & facts
├── 05_gold.sql                              # gold views + materialized view
├── 06_metric_view.sql                       # Unity Catalog metric view (YAML)
├── 07_governance.sql                        # initial column masks + row filter (account-group based)
├── 07b_governance_fix.sql                   # admin bypass for demo workspace
├── 07c_governance_demo_persona.sql          # live persona-override table for the demo
├── build_dashboard.py                       # programmatic Lakeview dashboard creation
├── build_genie.py                           # populates Genie space with curated questions + instructions + SQL
├── load_benchmarks.py                       # adds 12 benchmark Q+SQL pairs to the Genie space
├── benchmark_genie.py                       # Python harness that round-trips questions through Genie and times them
├── run_sql.py                               # tiny SQL helper using the Statement Execution API
├── DEMO_RUNBOOK.md                          # step-by-step talk track for the customer meeting
└── README.md                                # this file
```

---

## Deploy from scratch (≈10 minutes on a Small serverless warehouse)

### 0. Prereqs

- A Databricks workspace with **Unity Catalog** enabled
- A SQL warehouse (Serverless preferred — needed for materialized views and the metric view)
- The Databricks CLI installed and a profile authenticated to the workspace

### 1. Edit the constants

In `run_sql.py`, `build_dashboard.py`, `build_genie.py`, `load_benchmarks.py`, `benchmark_genie.py`, set:

| Constant | What to put |
|---|---|
| `PROFILE` | Your Databricks CLI profile name |
| `WAREHOUSE` | Your serverless SQL warehouse ID |
| `PARENT_PATH` (build_dashboard.py) | `/Users/<your-email>` |

In every `*.sql` file, replace `dazana_classic_ws_catalog` with the catalog you want to write into. (You can use `sed -i '' 's/dazana_classic_ws_catalog/<your_catalog>/g' *.sql`.)

You will also need a managed location on your catalog if Default Storage is not enabled.

### 2. Run the SQL files in order

```bash
chmod +x run_sql.py
./run_sql.py -f 01_setup_catalog.sql                                         # 4 schemas
./run_sql.py --catalog <catalog> --schema techo_bloc_bronze -f 02_bronze_d365.sql
./run_sql.py --catalog <catalog> --schema techo_bloc_bronze -f 03_bronze_legacy_and_other_sources.sql
./run_sql.py -f 04_silver.sql                                                # CTAS so column lineage is captured
./run_sql.py -f 05_gold.sql                                                  # views + materialized view
./run_sql.py -f 06_metric_view.sql                                           # YAML metric view
./run_sql.py -f 07_governance.sql                                            # column masks + RLS UDFs
./run_sql.py -f 07b_governance_fix.sql                                       # admin bypass
./run_sql.py -f 07c_governance_demo_persona.sql                              # persona override table
```

### 3. Build the dashboard

```bash
python3 build_dashboard.py
```

Returns a dashboard ID and Lakeview path. The script also publishes the dashboard so the URL works without further clicks.

To re-PATCH an existing dashboard: `python3 build_dashboard.py <dashboard_id>`.

### 4. Build the Genie space

You need the data-room/Genie space ID — create the space once via:

```bash
databricks api post /api/2.0/data-rooms --profile=<profile> --json='{
  "display_name": "Techo-Bloc — Sales & Finance Genie",
  "description": "...",
  "warehouse_id": "<warehouse_id>",
  "parent_path": "/Users/<your-email>",
  "table_identifiers": [
    "<catalog>.techo_bloc_silver.fact_invoice_lines",
    "<catalog>.techo_bloc_silver.fact_gl_transactions",
    "<catalog>.techo_bloc_silver.fact_crm_deals",
    "<catalog>.techo_bloc_silver.fact_web_engagement",
    "<catalog>.techo_bloc_silver.dim_customer",
    "<catalog>.techo_bloc_silver.dim_product",
    "<catalog>.techo_bloc_silver.dim_region",
    "<catalog>.techo_bloc_silver.dim_date",
    "<catalog>.techo_bloc_gold.vw_customer_360",
    "<catalog>.techo_bloc_gold.vw_ar_aging",
    "<catalog>.techo_bloc_gold.vw_finance_kpis",
    "<catalog>.techo_bloc_gold.mv_sales_summary",
    "<catalog>.techo_bloc_gold.metrics_techo_bloc"
  ]
}'
```

Paste the returned `space_id` into `build_genie.py`, `load_benchmarks.py`, and `benchmark_genie.py`. Then:

```bash
python3 build_genie.py        # 12 sample questions, 8 text + 8 SQL instructions
python3 load_benchmarks.py    # 12 benchmarks (visible under the Benchmarks tab)
```

### 5. Smoke test

```bash
python3 benchmark_genie.py            # round-trips all 12 questions through Genie, prints latency + SQL
```

Expect ≈ p50 11s, p95 19s on a Small Serverless warehouse, and 100% completion. Output goes to `benchmark_results.md`.

---

## The governance demo (the part Matt cares about)

A persona-override table maps users to roles so you can flip between them mid-demo:

```sql
UPDATE <catalog>.techo_bloc_governance.demo_persona
   SET persona = 'GLOBAL_LEADERSHIP',  -- or HR, FINANCE, SALES_LEADER, SALES_REP,
                                        --    REGIONAL_MGR_US_EAST/_US_WEST/_CA_EAST/_CA_WEST
       set_at  = current_timestamp()
 WHERE user_email = current_user();
```

| Persona | PII (email/phone/addr) | SSN | Salary | Territories |
|---|---|---|---|---|
| `GLOBAL_LEADERSHIP` | full | masked | masked | all |
| `HR` | full | full | full | all |
| `FINANCE` | full | masked | full | all |
| `SALES_LEADER` | phone visible | masked | masked | all |
| `SALES_REP` | masked | masked | masked | all |
| `REGIONAL_MGR_US_EAST` | masked | masked | masked | US-East only |
| `REGIONAL_MGR_US_WEST` | masked | masked | masked | US-West only |
| `REGIONAL_MGR_CA_EAST` | masked | masked | masked | Canada-East only |
| `REGIONAL_MGR_CA_WEST` | masked | masked | masked | Canada-West only |

In production, replace the `demo_persona` lookup with real account groups (`techo_hr`, `techo_finance`, `techo_us_east`, …). The masking and row-filter UDFs already check `is_account_group_member(...)` as a fallback.

The full list of governance demo questions, ordered by impact, is in [`DEMO_RUNBOOK.md`](DEMO_RUNBOOK.md).

---

## What this is *not*

- It is not a Lakeflow Connect demo — D365 ingestion is simulated via SQL, not Lakeflow. (Lakeflow Connect for D365 would replace the bronze step in production.)
- It is not a streaming demo — `fact_*` tables are batch-loaded once.
- The synthetic data is intentionally small (≈ 1M rows total). The story holds at scale; the demo just renders fast.
- It does not provision account-level groups. The `demo_persona` table is a stand-in so you can demo masking/RLS without SCIM ceremony.

---

## License

Internal Databricks demo content. Synthetic data only — no real Techo-Bloc data is included.

Built with [Vibe](https://github.com/databricks-field-engineering/vibe) and Claude Code.
