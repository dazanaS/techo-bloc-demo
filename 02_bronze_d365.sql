-- ============================================================
-- Bronze layer: D365 F&O tables (mimicking Synapse Link export shape)
-- Names follow real D365 conventions so column lineage demos make sense
-- ============================================================
-- ------------------------------------------------------------
-- D365 InventTable (Product master) ~ 240 SKUs
-- ------------------------------------------------------------
CREATE OR REPLACE TABLE d365_inventtable
COMMENT 'D365 InventTable: item/product master, landed from Synapse Link to ADLS Gen2'
TBLPROPERTIES (delta.feature.allowColumnDefaults = 'supported', source_system='D365_FO', source_path='Tables/InventTable')
AS
WITH groups AS (
  SELECT * FROM VALUES
    ('PAV','Pavers'),       ('SLB','Slabs'),       ('RTW','RetainingWalls'),
    ('PCP','PoolCoping'),   ('STP','OutdoorSteps'),('FIR','FirePits'),
    ('MAS','Masonry'),      ('ACC','Accessories')
  AS t(group_code, group_name)
),
collections AS (
  SELECT * FROM VALUES
    ('Mista'),('Borealis'),('Blu60'),('Travertina'),('Industria'),
    ('Squadra'),('Antika'),('Aberdeen'),('Hexa'),('Polara')
  AS t(collection)
)
SELECT
  CONCAT('ITM', LPAD(CAST(id AS STRING), 5, '0'))                        AS ITEMID,
  CONCAT(g.group_name, ' ', c.collection, ' ', CAST(60 + (id % 40) AS STRING), 'mm')
                                                                          AS ITEMNAME,
  g.group_code                                                            AS ITEMGROUPID,
  CASE WHEN id % 7 = 0 THEN 'Premium' WHEN id % 3 = 0 THEN 'Standard' ELSE 'Core' END
                                                                          AS PRODUCTSUBTYPE,
  CASE WHEN g.group_code IN ('PAV','SLB','MAS') THEN 'sf'
       WHEN g.group_code IN ('RTW','PCP','STP') THEN 'lf' ELSE 'each' END AS SALESUNIT,
  ROUND(2.50 + (CAST(abs(hash(id)) % 38000 AS DOUBLE) / 1000.0), 2)       AS UNITCOST_USD,
  ROUND(5.00 + (CAST(abs(hash(id+1)) % 75000 AS DOUBLE) / 1000.0), 2)     AS LISTPRICE_USD,
  CASE WHEN id % 11 = 0 THEN 1 ELSE 0 END                                 AS DISCONTINUED,
  CAST(date_add(DATE'2018-01-01', CAST((id * 7) % 2200 AS INT)) AS TIMESTAMP)
                                                                          AS CREATEDDATETIME,
  'USMF'                                                                  AS DATAAREAID
FROM (SELECT id, MOD(id, 8) AS gi, MOD(id, 10) AS ci FROM range(240)) r
JOIN groups       g  ON r.gi = (length(g.group_code) % 8)  -- pseudo-join to vary groups
JOIN collections  c  ON r.ci = (length(c.collection) % 10)
WHERE 1=1
LIMIT 240;

-- ------------------------------------------------------------
-- D365 CustTable (Customer master) ~ 4,800 customers, with PII
-- ------------------------------------------------------------
CREATE OR REPLACE TABLE d365_custtable
COMMENT 'D365 CustTable: customer master with PII (email, phone, address) — masked downstream'
TBLPROPERTIES (source_system='D365_FO', source_path='Tables/CustTable', contains_pii='true')
AS
WITH first_names AS (
  SELECT * FROM VALUES ('Alex'),('Jordan'),('Morgan'),('Taylor'),('Casey'),('Jamie'),('Riley'),('Drew'),('Skyler'),('Avery')
  AS t(fn)
),
last_names AS (
  SELECT * FROM VALUES ('Tremblay'),('Gagnon'),('Roy'),('Bouchard'),('Smith'),('Johnson'),('Brown'),('Davis'),('Miller'),('Wilson')
  AS t(ln)
),
states AS (
  SELECT * FROM VALUES
    ('NY','US-East'),('NJ','US-East'),('PA','US-East'),('MA','US-East'),('VA','US-East'),
    ('FL','US-East'),('OH','US-East'),('NC','US-East'),
    ('CA','US-West'),('WA','US-West'),('TX','US-West'),('AZ','US-West'),('CO','US-West'),
    ('QC','Canada-East'),('ON','Canada-East'),('NS','Canada-East'),
    ('BC','Canada-West'),('AB','Canada-West')
  AS t(state, territory)
)
SELECT
  CONCAT('CUST', LPAD(CAST(r.id AS STRING), 6, '0'))                            AS ACCOUNTNUM,
  CONCAT(fn.fn, ' ', ln.ln,
         CASE WHEN r.id % 4 = 0 THEN ' Landscaping LLC' WHEN r.id % 4 = 1 THEN ' Construction Inc' ELSE '' END)
                                                                                AS NAME,
  LOWER(CONCAT(fn.fn, '.', ln.ln, r.id, '@', element_at(array('gmail.com','outlook.com','yahoo.com','hotmail.com','techo-pro.example.com'), 1 + CAST(r.id % 5 AS INT))))
                                                                                AS EMAIL,
  CONCAT('+1-', LPAD(CAST(200 + (r.id % 700) AS STRING),3,'0'), '-',
         LPAD(CAST(100 + (r.id*17 % 900) AS STRING),3,'0'), '-',
         LPAD(CAST((r.id*31) % 10000 AS STRING),4,'0'))                          AS PHONE,
  CONCAT(CAST(100 + (r.id*23 % 9000) AS STRING), ' ',
         element_at(array('Maple','Oak','Cedar','Birch','Pine','Granite','Quartz'), 1 + CAST(r.id % 7 AS INT)),
         ' ',
         element_at(array('Ave','St','Rd','Blvd','Way'), 1 + CAST(r.id % 5 AS INT)))
                                                                                AS ADDRESS_LINE1,
  element_at(array('Brooklyn','Queens','Boston','Philadelphia','Toronto','Montreal','Quebec City','Halifax','Vancouver','Calgary','Los Angeles','San Diego','Phoenix','Denver','Houston','Dallas','Miami','Charlotte','Columbus','Newark'),
             1 + CAST(r.id % 20 AS INT))                                         AS CITY,
  s.state                                                                        AS STATE_PROVINCE,
  CONCAT(LPAD(CAST(r.id*7 % 100000 AS STRING), 5, '0'))                          AS POSTAL_CODE,
  CASE WHEN s.state IN ('QC','ON','NS','BC','AB') THEN 'CA' ELSE 'US' END        AS COUNTRY,
  s.territory                                                                    AS TERRITORY,
  CASE WHEN r.id % 100 < 55 THEN 'HOMEOWNER'
       WHEN r.id % 100 < 90 THEN 'CONTRACTOR'
       ELSE 'COMMERCIAL' END                                                     AS CUSTGROUP,
  CASE WHEN r.id % 137 = 0 THEN 1 ELSE 0 END                                     AS BLOCKED,
  ROUND(5000 + (CAST(abs(hash(r.id)) % 95000000 AS DOUBLE) / 1000.0), 2)         AS CREDITLIMIT_USD,
  CAST(date_add(DATE'2014-01-01', CAST(r.id*3 % 4380 AS INT)) AS TIMESTAMP)      AS CREATEDDATETIME,
  CAST(date_add(DATE'2024-01-01', CAST(r.id*2 % 800 AS INT)) AS TIMESTAMP)       AS MODIFIEDDATETIME,
  'USMF'                                                                         AS DATAAREAID
FROM (SELECT id, MOD(id, 10) AS fi, MOD(id, 10) AS li, MOD(id, 18) AS si FROM range(4800)) r
JOIN first_names fn ON r.fi = (length(fn.fn) % 10)
JOIN last_names  ln ON r.li = (length(ln.ln) % 10)
JOIN states      s  ON r.si = (length(s.state) % 18)
LIMIT 4800;

-- ------------------------------------------------------------
-- D365 CustInvoiceTrans (Invoice lines) ~ 80K rows over 2 yrs since D365 cutover
-- ------------------------------------------------------------
CREATE OR REPLACE TABLE d365_custinvoicetrans
COMMENT 'D365 CustInvoiceTrans: invoice lines posted in D365 F&O since 2025 cutover'
TBLPROPERTIES (source_system='D365_FO', source_path='Tables/CustInvoiceTrans')
AS
WITH base AS (
  SELECT
    id,
    CONCAT('INV-D-', LPAD(CAST((id DIV 3) AS STRING), 7, '0'))                  AS INVOICEID,
    CAST(1 + (id % 3) AS INT)                                                    AS LINENUM,
    CONCAT('CUST', LPAD(CAST(((id * 13) % 4800) + 1 AS STRING), 6, '0'))         AS INVOICEACCOUNT,
    CONCAT('ITM',  LPAD(CAST(((id * 7)  % 240)  + 1 AS STRING), 5, '0'))         AS ITEMID,
    date_add(DATE'2025-01-01', CAST(id*3 % 480 AS INT))                          AS INVOICEDATE,
    1 + CAST(abs(hash(id)) % 350 AS INT)                                         AS QTY,
    ROUND(5.00 + (CAST(abs(hash(id+1)) % 75000 AS DOUBLE) / 1000.0), 2)           AS SALESPRICE
  FROM range(80000) AS t(id)
)
SELECT
  INVOICEID, LINENUM, INVOICEACCOUNT, ITEMID, INVOICEDATE,
  CAST(QTY AS INT)                       AS QTY,
  SALESPRICE,
  ROUND(QTY * SALESPRICE, 2)             AS LINEAMOUNT,
  ROUND(QTY * SALESPRICE * 0.08, 2)      AS TAXAMOUNT,
  'USD'                                  AS CURRENCYCODE,
  'USMF'                                 AS DATAAREAID,
  CAST(INVOICEDATE AS TIMESTAMP)         AS POSTEDDATETIME,
  -- D365 Synapse Link `_SysRowId` style audit columns
  CONCAT('SR', sha1(CAST(INVOICEID || LINENUM AS STRING)))                       AS _SYSROWID,
  CAST(INVOICEDATE AS TIMESTAMP)                                                 AS _SINKMODIFIEDTIME
FROM base;

-- ------------------------------------------------------------
-- D365 MarkupTrans (Charges: freight, discount, etc.) ~ 12K rows
-- Linked to CustInvoiceTrans via INVOICEID — interdependency demo
-- ------------------------------------------------------------
CREATE OR REPLACE TABLE d365_markuptrans
COMMENT 'D365 MarkupTrans: charges (freight, discount, tax) tied to invoice; resolved into invoice totals downstream'
TBLPROPERTIES (source_system='D365_FO', source_path='Tables/MarkupTrans')
AS
WITH inv_ids AS (
  SELECT DISTINCT INVOICEID, INVOICEDATE
  FROM d365_custinvoicetrans
),
sample_inv AS (
  SELECT INVOICEID, INVOICEDATE, ROW_NUMBER() OVER (ORDER BY INVOICEID) AS rn
  FROM inv_ids
)
SELECT
  CONCAT('MK-', sha1(INVOICEID), '-', mc.code)                                   AS RECID,
  INVOICEID,
  mc.code                                                                        AS MARKUPCODE,
  CASE mc.code
    WHEN 'FREIGHT'  THEN ROUND(25.0 + (CAST(abs(hash(rn))   % 175000 AS DOUBLE) / 1000.0), 2)
    WHEN 'DISCOUNT' THEN -ROUND(5.0  + (CAST(abs(hash(rn+1)) % 250000 AS DOUBLE) / 1000.0), 2)
    WHEN 'PALLET'   THEN 45.00
  END                                                                            AS VALUE,
  CASE mc.code
    WHEN 'DISCOUNT' THEN '4101-DiscountsAllowed'
    WHEN 'FREIGHT'  THEN '5210-FreightOut'
    WHEN 'PALLET'   THEN '5215-PalletCharges' END                                AS MARKUPACCOUNT,
  CAST(INVOICEDATE AS TIMESTAMP)                                                 AS TRANSDATE,
  'USMF'                                                                         AS DATAAREAID
FROM sample_inv s
JOIN (SELECT * FROM VALUES ('FREIGHT'),('DISCOUNT'),('PALLET') AS t(code)) mc
  ON (s.rn % 3 = (length(mc.code) % 3));

-- ------------------------------------------------------------
-- D365 DimensionAttributeValueCombination (financial dimensions: BU + Channel)
-- ------------------------------------------------------------
CREATE OR REPLACE TABLE d365_dimensionvalues
COMMENT 'D365 DimensionAttributeValueCombination: business unit + sales channel dimension master'
AS
SELECT * FROM VALUES
  ('BU-RES','Residential','CHN-DEALER',  'Dealer Network'),
  ('BU-RES','Residential','CHN-DIRECT',  'Direct to Homeowner'),
  ('BU-COM','Commercial', 'CHN-DEALER',  'Dealer Network'),
  ('BU-COM','Commercial', 'CHN-PROJECT', 'Commercial Project'),
  ('BU-PRO','Pro/Contractor','CHN-PRO',  'Pro Loyalty Program'),
  ('BU-PRO','Pro/Contractor','CHN-DEALER','Dealer Network')
AS t(BU_CODE, BU_NAME, CHANNEL_CODE, CHANNEL_NAME);
