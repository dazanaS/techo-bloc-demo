-- ============================================================
-- Metric view: Techo-Bloc KPIs
-- Defined as a Unity Catalog metric view (YAML) over the silver fact + dims
-- This is what Genie should consume so KPIs are consistent across BI tools.
-- ============================================================

CREATE OR REPLACE VIEW dazana_classic_ws_catalog.techo_bloc_gold.metrics_techo_bloc
WITH METRICS
LANGUAGE YAML
COMMENT 'Techo-Bloc KPIs: Net Revenue, Gross Margin %, Discount %, Customer LTV, AR Aging, Pipeline. Use this in Genie for consistent KPI definitions.'
AS $$
version: 0.1
source: dazana_classic_ws_catalog.techo_bloc_silver.fact_invoice_lines
filter: invoice_date >= '2019-01-01'

joins:
  - name: customer
    source: dazana_classic_ws_catalog.techo_bloc_silver.dim_customer
    'on': source.customer_key = customer.customer_key
  - name: product
    source: dazana_classic_ws_catalog.techo_bloc_silver.dim_product
    'on': source.product_key = product.product_key

dimensions:
  - name: Invoice Month
    expr: date_trunc('MONTH', source.invoice_date)
  - name: Invoice Year
    expr: year(source.invoice_date)
  - name: Invoice Quarter
    expr: concat(year(source.invoice_date),'-Q',quarter(source.invoice_date))
  - name: Source System
    expr: source.source_system
  - name: Territory
    expr: customer.territory
  - name: Country
    expr: customer.country
  - name: Customer Segment
    expr: customer.customer_segment
  - name: Product Line
    expr: product.product_line
  - name: Product Tier
    expr: product.product_tier

measures:
  - name: Invoice Count
    expr: COUNT(DISTINCT source.invoice_id)
  - name: Line Count
    expr: COUNT(*)
  - name: Units Sold
    expr: SUM(source.quantity)
  - name: Gross Revenue
    expr: SUM(source.gross_line_amount)
  - name: Discounts
    expr: SUM(source.discount_amount)
  - name: Freight & Pallet
    expr: SUM(source.freight_amount + source.pallet_amount)
  - name: Net Revenue
    expr: SUM(source.net_invoice_amount)
  - name: Estimated COGS
    expr: SUM(source.quantity * product.unit_cost_usd)
  - name: Estimated Gross Margin
    expr: SUM(source.net_invoice_amount) - SUM(source.quantity * product.unit_cost_usd)
  - name: Gross Margin Pct
    expr: |
      CASE WHEN SUM(source.net_invoice_amount) = 0 THEN 0
           ELSE (SUM(source.net_invoice_amount) - SUM(source.quantity * product.unit_cost_usd))
                / SUM(source.net_invoice_amount) END
  - name: Discount Pct
    expr: |
      CASE WHEN SUM(source.gross_line_amount) = 0 THEN 0
           ELSE -SUM(source.discount_amount) / SUM(source.gross_line_amount) END
  - name: Average Invoice Value
    expr: |
      CASE WHEN COUNT(DISTINCT source.invoice_id) = 0 THEN 0
           ELSE SUM(source.net_invoice_amount) / COUNT(DISTINCT source.invoice_id) END
  - name: Active Customers
    expr: COUNT(DISTINCT source.customer_key)
$$;
