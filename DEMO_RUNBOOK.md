# Techo-Bloc — Databricks AI/BI Demo Runbook

Built for Vinod's Thursday meeting with Matt. The decision-maker conversation is **cost + governance + AI/BI**, with the gold layer + Genie front-end being the show.

## Workspace
- **Workspace:** `Dazana-classic-ws` — https://fevm-dazana-classic-ws.cloud.databricks.com
- **CLI profile:** `Dazana-classic-ws-pat`
- **Catalog:** `dazana_classic_ws_catalog`
- **Schemas:** `techo_bloc_bronze`, `techo_bloc_silver`, `techo_bloc_gold`, `techo_bloc_governance`
- **Warehouse:** `Serverless Starter Warehouse` (`a82088b3bfe8752c`)

## Demo Artifacts

| Asset | URL |
|---|---|
| **Dashboard** | https://fevm-dazana-classic-ws.cloud.databricks.com/dashboardsv3/01f143e38a671f26b230134736684951 |
| **Genie Space** | https://fevm-dazana-classic-ws.cloud.databricks.com/genie/rooms/01f143e3caf119e3b09d967d4ef4fc91 |
| **Catalog Explorer** | https://fevm-dazana-classic-ws.cloud.databricks.com/explore/data/dazana_classic_ws_catalog |

## Bronze → Silver → Gold (rows)

| Layer | Table | Rows | Notes |
|---|---|---:|---|
| bronze | `d365_inventtable` | 192 | D365 product master |
| bronze | `d365_custtable` | 4,800 | D365 customer master (PII) |
| bronze | `d365_custinvoicetrans` | 80,000 | D365 invoice lines (post-2025 cutover) |
| bronze | `d365_markuptrans` | 80,000 | D365 freight/discount/pallet (interdependent with CustInvoiceTrans) |
| bronze | `d365_dimensionvalues` | 6 | BU + channel financial dim |
| bronze | `ax2012_custinvoicejour` | 28,000 | Legacy AX invoice headers (2019-2024) |
| bronze | `ax2012_gl_transactions` | 599,998 | **5+ years of GL — the 1GB Power BI cap killer** |
| bronze | `ukg_employees` | 756 | UKG HR feed (PII: SSN, salary) |
| bronze | `hubspot_deals` | 8,500 | CRM deals |
| bronze | `ga_sessions` | 150,000 | Google Analytics |
| silver | `dim_customer / dim_product / dim_employee / dim_region / dim_date` | 4,800 / 192 / 756 / 4 / 3,652 | Conformed Kimball dims |
| silver | `fact_invoice_lines` | 108,000 | **D365 + AX 2012 unified, MarkupTrans applied** |
| silver | `fact_gl_transactions` | 599,998 | 5+ years cleaned |
| silver | `fact_web_engagement` | 150,000 | GA cleaned |
| silver | `fact_crm_deals` | 8,500 | HubSpot cleaned |
| gold | `mv_sales_summary` | MV | **Materialized monthly sales** |
| gold | `vw_dim_customer / vw_dim_employee` | views | PII surfaces (masked) |
| gold | `vw_finance_kpis` | view | Multi-year GL aggregates |
| gold | `vw_customer_360` | view | 360 = sales + CRM + web |
| gold | `vw_ar_aging` | view | AR aging buckets |
| gold | `metrics_techo_bloc` | metric view | **YAML KPI definitions used by Genie** |

## Talk Track (for Vinod / Matt)

### 1. Open the **Catalog Explorer** at `dazana_classic_ws_catalog.techo_bloc_silver.fact_invoice_lines`
- Click **Lineage** (column-level). Show how `fact_invoice_lines.net_invoice_amount` traces back to D365 `CustInvoiceTrans.LINEAMOUNT` and `MarkupTrans.VALUE` — exactly the column-lineage gap they flagged.
- Click **Sample Data** — preview shows realistic D365 + AX 2012 data unified in one table.
- Show the **Properties** tab: TBLPROPERTIES include `source_system='D365_FO'` and `source_path='Tables/CustInvoiceTrans'` — automatic provenance.

### 2. **Medallion + MarkupTrans story** — `dazana_classic_ws_catalog.techo_bloc_silver.fact_invoice_lines`
"This silver table is the entity-resolved invoice line. It rolls up `CustInvoiceTrans` and `MarkupTrans` so freight, discounts, and pallet charges automatically flow into your invoice totals — exactly the interdependency you mentioned. Same pattern handles AX 2012 historicals; one table for finance to query."

### 3. **The 1GB Power BI cap killer** — Open the dashboard tile **'Multi-year GL trend'**
"That tile reads 600K GL rows over five years through a serverless SQL Warehouse. In Power BI Pro you'd hit the 1GB semantic model cap; here it renders in under a second and refreshes on demand."

### 4. **Governance demo (column masking + RLS)** — Open a SQL editor
```sql
-- Currently as Global Leadership: full PII visible, all territories
SELECT customer_key, email, phone, address_line1, territory
FROM dazana_classic_ws_catalog.techo_bloc_silver.dim_customer
LIMIT 5;

-- Flip persona → Sales Rep (PII masked, all territories)
UPDATE dazana_classic_ws_catalog.techo_bloc_governance.demo_persona
SET persona = 'SALES_REP', set_at = current_timestamp()
WHERE user_email = current_user();

SELECT customer_key, email, phone, address_line1, territory
FROM dazana_classic_ws_catalog.techo_bloc_silver.dim_customer
LIMIT 5;
-- Expect: ***@outlook.com  ***-***-1736  [REDACTED]  Canada-West

-- Flip persona → Regional Manager US-East (RLS narrows to US-East only)
UPDATE dazana_classic_ws_catalog.techo_bloc_governance.demo_persona
SET persona = 'REGIONAL_MGR_US_EAST', set_at = current_timestamp()
WHERE user_email = current_user();

SELECT territory, COUNT(*) AS rows
FROM dazana_classic_ws_catalog.techo_bloc_silver.dim_customer
GROUP BY territory;
-- Expect: only US-East — RLS filtered the rest

-- Reset for the rest of the demo
UPDATE dazana_classic_ws_catalog.techo_bloc_governance.demo_persona
SET persona = 'GLOBAL_LEADERSHIP', set_at = current_timestamp()
WHERE user_email = current_user();
```

> The mask UDFs are in `techo_bloc_governance.mask_email / mask_phone / mask_address / mask_ssn / mask_salary`.
> The row filter is `techo_bloc_governance.row_filter_territory`.
> In production, replace the demo-persona table with real account groups (`techo_hr`, `techo_finance`, `techo_us_east`, …). The UDFs already check `is_account_group_member(...)` as a fallback.

### 5. **Genie / metric view** — Open the Genie space and run two questions
1. *"What is our total net revenue by product line over the last year?"*
   - Genie picks the **metric view** (`gold.metrics_techo_bloc`) because the general instructions tell it to. Shows `MEASURE(\`Net Revenue\`)` on `Product Line`. Same KPI definition Power BI / Excel will see.
2. *"Which contractors had open pipeline > $100K but no invoice activity in the last 90 days?"*
   - Genie joins `dim_customer` (segment = CONTRACTOR), `fact_crm_deals` (deal_outcome = OPEN), `fact_invoice_lines`. The trusted SQL example is already in the space, so it lands fast.

### 6. **Materialized view + cost story** — `gold.mv_sales_summary`
"This is a serverless DLT-backed materialized view. It refreshes incrementally on a schedule, costs nothing when not refreshing, and your dashboard hits a tiny pre-aggregated table. We sized 200 hours/month of warehouse — total ~$7K, including ETL and ad-hoc."

## Persona quick-flip cheatsheet

```sql
-- Run this in the SQL editor or a notebook to flip personas mid-demo.
UPDATE dazana_classic_ws_catalog.techo_bloc_governance.demo_persona
   SET persona = 'GLOBAL_LEADERSHIP',  -- or HR, FINANCE, SALES_LEADER, SALES_REP,
                                        --    REGIONAL_MGR_US_EAST, REGIONAL_MGR_US_WEST,
                                        --    REGIONAL_MGR_CA_EAST, REGIONAL_MGR_CA_WEST
       set_at  = current_timestamp()
 WHERE user_email = current_user();
```

| Persona | PII | Territories |
|---|---|---|
| `GLOBAL_LEADERSHIP` | full | all |
| `HR` | full + SSN + salary | all |
| `FINANCE` | full + salary | all |
| `SALES_LEADER` | phone visible | all |
| `SALES_REP` | masked | all |
| `REGIONAL_MGR_US_EAST` | masked | US-East only |
| `REGIONAL_MGR_US_WEST` | masked | US-West only |
| `REGIONAL_MGR_CA_EAST` | masked | Canada-East only |
| `REGIONAL_MGR_CA_WEST` | masked | Canada-West only |

## Source files

All SQL/Python lives in `/Users/dazana.hasan/Documents/Vibe_setup/techo_bloc_demo/`:
- `01_setup_catalog.sql` — schemas
- `02_bronze_d365.sql` — D365 bronze
- `03_bronze_legacy_and_other_sources.sql` — AX 2012 + UKG/HubSpot/GA
- `04_silver.sql` — silver dims/facts
- `05_gold.sql` — gold views + materialized view
- `06_metric_view.sql` — metric view (YAML)
- `07_governance.sql` — initial column masks + row filter (account-group based)
- `07b_governance_fix.sql` — admin bypass for demo workspace
- `07c_governance_demo_persona.sql` — live-demo persona override
- `build_dashboard.py` — Lakeview dashboard builder
- `build_genie.py` — Genie space curated questions / instructions / SQL examples
- `run_sql.py` — helper to run SQL via the warehouse
