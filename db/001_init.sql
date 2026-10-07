BEGIN;

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE SCHEMA IF NOT EXISTS metadata;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS geo;
CREATE SCHEMA IF NOT EXISTS fato;
CREATE SCHEMA IF NOT EXISTS analytics;

CREATE TABLE IF NOT EXISTS metadata.fontes (
    id_fonte BIGSERIAL PRIMARY KEY,
    codigo TEXT NOT NULL UNIQUE,
    nome TEXT NOT NULL,
    instituicao TEXT,
    tipo_origem TEXT,
    periodicidade TEXT,
    url_principal TEXT,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS metadata.coletas (
    id_coleta BIGSERIAL PRIMARY KEY,
    id_fonte BIGINT NOT NULL REFERENCES metadata.fontes(id_fonte),
    data_coleta TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    data_referencia DATE,
    referencia_texto TEXT,
    origem TEXT,
    caminho_storage TEXT,
    sha256 CHAR(64),
    tamanho_bytes BIGINT,
    registros BIGINT,
    status TEXT NOT NULL DEFAULT 'ok',
    observacao TEXT,
    extras JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_coletas_fonte_data
    ON metadata.coletas (id_fonte, data_coleta DESC);

CREATE INDEX IF NOT EXISTS idx_coletas_referencia
    ON metadata.coletas (data_referencia);

CREATE INDEX IF NOT EXISTS idx_coletas_sha256
    ON metadata.coletas (sha256)
    WHERE sha256 IS NOT NULL;

INSERT INTO metadata.fontes (codigo, nome, instituicao, tipo_origem)
VALUES
    ('abve', 'ABVE', 'ABVE', 'arquivo'),
    ('aneel', 'ANEEL', 'ANEEL', 'arquivo/API'),
    ('anp', 'ANP', 'ANP', 'arquivo'),
    ('fipe', 'FIPE', 'FIPE/Parallelum', 'API'),
    ('ibge', 'IBGE', 'IBGE', 'arquivo'),
    ('inmetro', 'INMETRO/PBEV', 'INMETRO', 'arquivo'),
    ('od2023', 'Pesquisa Origem e Destino 2023', 'Metrô de São Paulo', 'arquivo'),
    ('senatran', 'SENATRAN', 'SENATRAN', 'arquivo'),
    ('uber', 'Uber - regras e elegibilidade', 'Uber', 'arquivo/web'),
    ('uber_match', 'Uber Match', 'Uber', 'web/snapshot'),
    ('open_charge_map', 'Open Charge Map', 'Open Charge Map', 'API')
ON CONFLICT (codigo) DO UPDATE
SET
    nome = EXCLUDED.nome,
    instituicao = EXCLUDED.instituicao,
    tipo_origem = EXCLUDED.tipo_origem;

COMMIT;
