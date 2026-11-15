-- PI06 | Migration 006 | API v1 (snapshots analíticos, sem vínculos FIPE/OD artificiais)
-- Executar no banco PostgreSQL/PostGIS de desenvolvimento; depende somente de PostGIS.
-- Camada independente das views 005: publica os 8 CSVs como snapshot transacional.
BEGIN;
CREATE SCHEMA IF NOT EXISTS extensions;
CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA extensions;
SET LOCAL search_path TO public, extensions, pg_catalog;
CREATE SCHEMA IF NOT EXISTS api_v1;

CREATE TABLE IF NOT EXISTS api_v1.od_municipios (
 municipio_od_id integer PRIMARY KEY CHECK (municipio_od_id BETWEEN 1 AND 39),
 municipio_nome text NOT NULL, qtd_zonas integer NOT NULL CHECK(qtd_zonas>0),
 zonas_com_amostra_origem integer NOT NULL, zonas_com_amostra_destino integer NOT NULL,
 viagens_origem_amostra numeric, viagens_origem_expandidas numeric,
 viagens_destino_amostra numeric, viagens_destino_expandidas numeric,
 fonte text NOT NULL, natureza_dado text NOT NULL
);
CREATE TABLE IF NOT EXISTS api_v1.od_distritos_capital (
 distrito_od_id integer PRIMARY KEY, distrito_nome text NOT NULL,
 qtd_zonas integer NOT NULL, zonas_com_amostra_origem integer NOT NULL,
 zonas_com_amostra_destino integer NOT NULL,
 viagens_origem_amostra numeric, viagens_origem_expandidas numeric,
 viagens_destino_amostra numeric, viagens_destino_expandidas numeric,
 fonte text NOT NULL, natureza_dado text NOT NULL
);
CREATE TABLE IF NOT EXISTS api_v1.od_zonas (
 zona_od_id integer PRIMARY KEY CHECK(zona_od_id BETWEEN 1 AND 527), zona_nome text NOT NULL,
 municipio_od_id integer NOT NULL REFERENCES api_v1.od_municipios(municipio_od_id),
 municipio_nome text NOT NULL, distrito_od_id integer NOT NULL,
 distrito_nome text NOT NULL, escopo text NOT NULL,
 viagens_origem_amostra numeric, viagens_origem_expandidas numeric,
 viagens_destino_amostra numeric, viagens_destino_expandidas numeric,
 tem_amostra_origem boolean NOT NULL, tem_amostra_destino boolean NOT NULL,
 fonte text NOT NULL, natureza_dado text NOT NULL, observacao text NOT NULL,
 CONSTRAINT ck_od_origem_nulo CHECK(tem_amostra_origem=(viagens_origem_amostra IS NOT NULL)),
 CONSTRAINT ck_od_destino_nulo CHECK(tem_amostra_destino=(viagens_destino_amostra IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS idx_api_v1_zonas_muni ON api_v1.od_zonas(municipio_od_id);
CREATE INDEX IF NOT EXISTS idx_api_v1_zonas_distrito ON api_v1.od_zonas(distrito_od_id);

CREATE TABLE IF NOT EXISTS api_v1.od_top_destinos (
 zona_origem_id integer NOT NULL REFERENCES api_v1.od_zonas(zona_od_id),
 zona_destino_id integer NOT NULL REFERENCES api_v1.od_zonas(zona_od_id),
 faixa_horaria text NOT NULL, viagens_amostra numeric NOT NULL,
 viagens_expandidas numeric NOT NULL, amostra_com_distancia integer,
 duracao_media_ponderada_min numeric, distancia_linha_reta_media_ponderada_km numeric,
 posicao integer NOT NULL CHECK(posicao BETWEEN 1 AND 5),
 nome_zona_destino text NOT NULL, municipio_destino text NOT NULL,
 fonte text NOT NULL, natureza_dado text NOT NULL, observacao text NOT NULL,
 PRIMARY KEY (zona_origem_id, faixa_horaria, zona_destino_id),
 UNIQUE (zona_origem_id, faixa_horaria, posicao)
);
CREATE INDEX IF NOT EXISTS idx_api_v1_od_destinos ON api_v1.od_top_destinos(zona_origem_id,faixa_horaria,posicao);

CREATE TABLE IF NOT EXISTS api_v1.energia_inmetro (
 inmetro_id text NOT NULL, marca_inmetro text, modelo_inmetro text, versao_inmetro text,
 tecnologia text, modalidade text NOT NULL,
 custo_energia_rs_km numeric NOT NULL CHECK(custo_energia_rs_km>=0),
 km_mes_hipotese numeric NOT NULL CHECK(km_mes_hipotese>0),
 custo_energia_rs_mes_hipotetico numeric,
 grupo_interface text NOT NULL, fonte text NOT NULL, natureza_dado text NOT NULL,
 observacao text NOT NULL, PRIMARY KEY(inmetro_id,modalidade)
);
CREATE INDEX IF NOT EXISTS idx_api_v1_energia_filtro ON api_v1.energia_inmetro(grupo_interface,modalidade);

CREATE TABLE IF NOT EXISTS api_v1.motorista_custos (
 perfil_id text NOT NULL, regime text NOT NULL, inmetro_id text NOT NULL,
 marca_inmetro text, modelo_inmetro text, versao_inmetro text, tecnologia text,
 modalidade text NOT NULL, status text NOT NULL,
 campos_pendentes text, fonte_premissas text, km_mes numeric NOT NULL CHECK(km_mes>0),
 receita_liquida_plataforma_rs_mes numeric,
 custo_total_economico_rs_mes numeric, resultado_economico_rs_mes numeric,
 custo_total_rs_km numeric, receita_equilibrio_rs_km numeric, receita_equilibrio_rs_hora numeric,
 componentes_custos_informados integer NOT NULL CHECK(componentes_custos_informados>=0),
 componentes_custos_pendentes integer NOT NULL CHECK(componentes_custos_pendentes>=0),
 subtotal_custos_conhecidos_rs_mes numeric,
 todos_custos_preenchidos boolean NOT NULL,
 grupo_interface text NOT NULL, fonte text NOT NULL, natureza_dado text NOT NULL,
 observacao text NOT NULL, PRIMARY KEY(perfil_id,inmetro_id,modalidade),
 FOREIGN KEY (inmetro_id,modalidade) REFERENCES api_v1.energia_inmetro(inmetro_id,modalidade),
 CHECK (componentes_custos_informados+componentes_custos_pendentes=11),
 CHECK (todos_custos_preenchidos=(componentes_custos_pendentes=0)),
 CHECK (componentes_custos_pendentes=0 OR custo_total_economico_rs_mes IS NULL),
 CHECK (status <> 'PARCIAL_PENDENTE' OR resultado_economico_rs_mes IS NULL)
);
CREATE INDEX IF NOT EXISTS idx_api_v1_motorista_filtros ON api_v1.motorista_custos(perfil_id,grupo_interface,status);

CREATE TABLE IF NOT EXISTS api_v1.premissas_receita (
 cenario_receita_id text PRIMARY KEY, titulo text NOT NULL,
 receita_apos_plataforma_rs_mes numeric NOT NULL CHECK(receita_apos_plataforma_rs_mes>=0),
 fonte text NOT NULL CHECK(fonte='HIPOTESE_DIDATICA_NAO_OBSERVADA'),
 observacao text NOT NULL, natureza_dado text NOT NULL
);
CREATE TABLE IF NOT EXISTS api_v1.sensibilidade_receita (
 perfil_id text NOT NULL, regime text NOT NULL, inmetro_id text NOT NULL,
 modalidade text NOT NULL, tecnologia text, grupo_interface text NOT NULL,
 km_mes numeric NOT NULL, custo_total_economico_rs_mes numeric,
 subtotal_custos_conhecidos_rs_mes numeric, componentes_custos_pendentes integer NOT NULL,
 campos_pendentes text, todos_custos_preenchidos boolean NOT NULL,
 cenario_receita_id text NOT NULL, receita_apos_plataforma_rs_mes numeric NOT NULL,
 resultado_economico_simulado_rs_mes numeric, resultado_simulado_rs_km numeric,
 situacao_calculo text NOT NULL, natureza_dado text NOT NULL, observacao text NOT NULL,
 PRIMARY KEY(perfil_id,inmetro_id,modalidade,cenario_receita_id),
 FOREIGN KEY(perfil_id,inmetro_id,modalidade) REFERENCES api_v1.motorista_custos(perfil_id,inmetro_id,modalidade),
 FOREIGN KEY(cenario_receita_id) REFERENCES api_v1.premissas_receita(cenario_receita_id),
 CHECK(componentes_custos_pendentes=0 OR resultado_economico_simulado_rs_mes IS NULL),
 CHECK(componentes_custos_pendentes=0 OR resultado_simulado_rs_km IS NULL),
 CHECK(componentes_custos_pendentes=0 OR custo_total_economico_rs_mes IS NULL)
);
CREATE INDEX IF NOT EXISTS idx_api_v1_sens_filtros ON api_v1.sensibilidade_receita(perfil_id,cenario_receita_id,grupo_interface);

CREATE TABLE IF NOT EXISTS api_v1.zonas_geometrias (
 zona_od_id integer PRIMARY KEY REFERENCES api_v1.od_zonas(zona_od_id),
 geom geometry(MultiPolygon,4326) NOT NULL,
 CHECK(ST_IsValid(geom)), CHECK(NOT ST_IsEmpty(geom))
);
CREATE INDEX IF NOT EXISTS idx_api_v1_zonas_geo ON api_v1.zonas_geometrias USING gist(geom);
CREATE TABLE IF NOT EXISTS api_v1.municipios_geometrias (
 municipio_od_id integer PRIMARY KEY REFERENCES api_v1.od_municipios(municipio_od_id),
 geom geometry(MultiPolygon,4326) NOT NULL,
 CHECK(ST_IsValid(geom)), CHECK(NOT ST_IsEmpty(geom))
);
CREATE INDEX IF NOT EXISTS idx_api_v1_muni_geo ON api_v1.municipios_geometrias USING gist(geom);

CREATE TABLE IF NOT EXISTS api_v1.recarga_pontos (
 id_posto bigint PRIMARY KEY, titulo text, operadora text, logradouro text, cidade text,
 estado_provincia text, cep text, latitude numeric, longitude numeric,
 qtd_conexoes integer, potencia_max_kw numeric, tipos_conectores text,
 status_cadastral text, custo_uso text, data_coleta text, fonte_url text,
 recorte_geografico text, geom geometry(Point,4326)
);
CREATE INDEX IF NOT EXISTS idx_api_v1_recarga_geom ON api_v1.recarga_pontos USING gist(geom);
CREATE TABLE IF NOT EXISTS api_v1.recarga_zonas (
 id_posto bigint PRIMARY KEY REFERENCES api_v1.recarga_pontos(id_posto),
 zona_od_id integer REFERENCES api_v1.od_zonas(zona_od_id),
 qtd_zonas_cobrem_ponto integer NOT NULL CHECK(qtd_zonas_cobrem_ponto>=0),
 situacao text NOT NULL CHECK(situacao IN ('ZONA_UNICA','SEM_ZONA','AMBIGUO','SEM_COORDENADAS'))
);
CREATE INDEX IF NOT EXISTS idx_api_v1_recarga_zonas ON api_v1.recarga_zonas(zona_od_id);

CREATE TABLE IF NOT EXISTS api_v1.carga_atual (
 id smallint PRIMARY KEY DEFAULT 1 CHECK(id=1),
 manifesto_sha256 char(64) NOT NULL, versao text NOT NULL,
 carregado_em timestamptz NOT NULL DEFAULT now(),
 contagens jsonb NOT NULL, zonas_com_geometria integer NOT NULL,
 pontos_recarga integer NOT NULL,
 observacoes text NOT NULL DEFAULT ''
);

COMMENT ON SCHEMA api_v1 IS 'Snapshots transacionais de exibição do PI06; fontes/simulações mantidas separadas por granularidade.';
COMMENT ON COLUMN api_v1.od_top_destinos.distancia_linha_reta_media_ponderada_km IS 'Linha reta, não km rodado pelo motorista';
COMMENT ON COLUMN api_v1.motorista_custos.subtotal_custos_conhecidos_rs_mes IS 'Subtotal parcial; NÃO custo total quando há lacunas';
COMMENT ON COLUMN api_v1.sensibilidade_receita.resultado_economico_simulado_rs_mes IS 'NULL quando custos incompletos; receita ilustrativa, não observada';
COMMIT;
