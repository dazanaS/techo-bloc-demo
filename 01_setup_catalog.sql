-- Use existing catalog; create Techo-Bloc demo schemas
USE CATALOG dazana_classic_ws_catalog;
CREATE SCHEMA IF NOT EXISTS techo_bloc_bronze     COMMENT 'Techo-Bloc demo: raw landed data from D365 F&O Synapse Link, AX 2012, UKG, HubSpot, GA';
CREATE SCHEMA IF NOT EXISTS techo_bloc_silver     COMMENT 'Techo-Bloc demo: cleaned, deduplicated, integrated dimensions and facts';
CREATE SCHEMA IF NOT EXISTS techo_bloc_gold       COMMENT 'Techo-Bloc demo: business-ready views, materialized views, metric view, customer 360';
CREATE SCHEMA IF NOT EXISTS techo_bloc_governance COMMENT 'Techo-Bloc demo: column masks and row-filter UDFs';
SHOW SCHEMAS IN dazana_classic_ws_catalog LIKE 'techo_bloc_*';
