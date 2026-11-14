-- PI06 — Modelo territorial OD 2023 (não aplica carga automaticamente).
-- Pré-requisito: db/001_init.sql (schemas e PostGIS).
-- Arquivos CSV: dados_relatorios/territorio_od2023/
-- GeoJSON de zonas: carregar após validar SHP; o SQL não inventa polígonos.
BEGIN;

CREATE SCHEMA IF NOT EXISTS geo;
CREATE SCHEMA IF NOT EXISTS fato;
CREATE SCHEMA IF NOT EXISTS analytics;
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS geo.municipios_od2023 (
    municipio_od_id INTEGER PRIMARY KEY CHECK (municipio_od_id BETWEEN 1 AND 39),
    municipio_nome TEXT NOT NULL,
    qtd_zonas INTEGER NOT NULL CHECK (qtd_zonas > 0)
);

CREATE TABLE IF NOT EXISTS geo.zonas_od2023 (
    zona_od_id INTEGER PRIMARY KEY CHECK (zona_od_id BETWEEN 1 AND 527),
    zona_nome TEXT NOT NULL,
    municipio_od_id INTEGER NOT NULL REFERENCES geo.municipios_od2023(municipio_od_id),
    municipio_nome TEXT NOT NULL,
    distrito_od_id INTEGER NOT NULL,
    distrito_nome TEXT NOT NULL,
    area_hectares NUMERIC(14,4) CHECK (area_hectares >= 0),
    escopo TEXT NOT NULL CHECK (escopo IN ('SAO_PAULO','RMSP_OUTROS')),
    correcao_codigo_municipio TEXT NOT NULL DEFAULT '',
    geom geometry(MultiPolygon,4326),
    CONSTRAINT ck_sp_id CHECK ((municipio_od_id = 36) = (escopo = 'SAO_PAULO'))
);
CREATE INDEX IF NOT EXISTS idx_od2023_zonas_muni ON geo.zonas_od2023(municipio_od_id);
CREATE INDEX IF NOT EXISTS idx_od2023_zonas_distrito ON geo.zonas_od2023(municipio_od_id,distrito_od_id);
CREATE INDEX IF NOT EXISTS idx_od2023_zonas_geom ON geo.zonas_od2023 USING gist(geom);

CREATE TABLE IF NOT EXISTS fato.od2023_origens_zona_faixa (
    zona_od_id INTEGER NOT NULL REFERENCES geo.zonas_od2023(zona_od_id),
    faixa_horaria TEXT NOT NULL,
    viagens_amostra BIGINT NOT NULL CHECK (viagens_amostra > 0),
    viagens_expandidas NUMERIC(20,4) NOT NULL CHECK (viagens_expandidas > 0),
    amostra_com_distancia BIGINT NOT NULL CHECK (amostra_com_distancia >= 0),
    duracao_media_ponderada_min NUMERIC(12,2),
    distancia_linha_reta_media_ponderada_km NUMERIC(12,3),
    PRIMARY KEY (zona_od_id,faixa_horaria)
);

CREATE TABLE IF NOT EXISTS fato.od2023_destinos_zona_faixa (
    zona_od_id INTEGER NOT NULL REFERENCES geo.zonas_od2023(zona_od_id),
    faixa_horaria TEXT NOT NULL,
    viagens_amostra BIGINT NOT NULL CHECK (viagens_amostra > 0),
    viagens_expandidas NUMERIC(20,4) NOT NULL CHECK (viagens_expandidas > 0),
    amostra_com_distancia BIGINT NOT NULL CHECK (amostra_com_distancia >= 0),
    duracao_media_ponderada_min NUMERIC(12,2),
    distancia_linha_reta_media_ponderada_km NUMERIC(12,3),
    PRIMARY KEY (zona_od_id,faixa_horaria)
);

CREATE TABLE IF NOT EXISTS fato.od2023_fluxos_zona_faixa (
    zona_origem_id INTEGER NOT NULL REFERENCES geo.zonas_od2023(zona_od_id),
    zona_destino_id INTEGER NOT NULL REFERENCES geo.zonas_od2023(zona_od_id),
    faixa_horaria TEXT NOT NULL,
    viagens_amostra BIGINT NOT NULL CHECK (viagens_amostra > 0),
    viagens_expandidas NUMERIC(20,4) NOT NULL CHECK (viagens_expandidas > 0),
    amostra_com_distancia BIGINT NOT NULL CHECK (amostra_com_distancia >= 0),
    duracao_media_ponderada_min NUMERIC(12,2),
    distancia_linha_reta_media_ponderada_km NUMERIC(12,3),
    PRIMARY KEY (zona_origem_id,zona_destino_id,faixa_horaria)
);
CREATE INDEX IF NOT EXISTS idx_od2023_fluxos_destino ON fato.od2023_fluxos_zona_faixa(zona_destino_id);

CREATE OR REPLACE VIEW analytics.od2023_indicadores_zona AS
SELECT z.zona_od_id,z.zona_nome,z.municipio_od_id,z.municipio_nome,
       z.distrito_od_id,z.distrito_nome,z.escopo,
       oo.viagens_amostra AS origens_amostra,
       oo.viagens_expandidas AS origens_expandidas,
       dd.viagens_amostra AS destinos_amostra,
       dd.viagens_expandidas AS destinos_expandidos,
       (oo.viagens_amostra IS NOT NULL) AS tem_amostra_origem,
       (dd.viagens_amostra IS NOT NULL) AS tem_amostra_destino,
       z.geom
FROM geo.zonas_od2023 z
LEFT JOIN (
  SELECT zona_od_id,SUM(viagens_amostra) AS viagens_amostra,
         SUM(viagens_expandidas) AS viagens_expandidas
  FROM fato.od2023_origens_zona_faixa GROUP BY zona_od_id
) oo USING (zona_od_id)
LEFT JOIN (
  SELECT zona_od_id,SUM(viagens_amostra) AS viagens_amostra,
         SUM(viagens_expandidas) AS viagens_expandidas
  FROM fato.od2023_destinos_zona_faixa GROUP BY zona_od_id
) dd USING (zona_od_id);

COMMENT ON COLUMN fato.od2023_fluxos_zona_faixa.distancia_linha_reta_media_ponderada_km IS
  'Distância em linha reta (m/1000), não quilometragem viária ou de motorista';
COMMENT ON VIEW analytics.od2023_indicadores_zona IS
  'Viagens táxi não convencional/aplicativo (MODOPRIN=12) na OD 2023; não são corridas Uber exclusivas.';
COMMIT;
