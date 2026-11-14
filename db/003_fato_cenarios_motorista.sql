-- PI06: executar apenas depois de verificar o esquema e backup.
-- Tabela preparada para carregamento posterior via COPY / ETL.
-- Não apaga tabelas existentes e não insere dados hipotéticos automaticamente.
CREATE SCHEMA IF NOT EXISTS analytics;
CREATE TABLE IF NOT EXISTS analytics.fato_cenarios_motorista (
    perfil_id text NOT NULL,
    regime text NOT NULL CHECK (regime IN ('proprio','alugado')),
    inmetro_id text NOT NULL,
    marca_inmetro text,
    modelo_inmetro text,
    versao_inmetro text,
    tecnologia text,
    modalidade text NOT NULL,
    km_mes numeric(15,4) NOT NULL CHECK (km_mes>0),
    receita_liquida_plataforma_rs_mes numeric(16,4),
    custo_energia_rs_mes numeric(16,4),
    custo_manutencao_rs_mes numeric(16,4),
    custo_pneus_rs_mes numeric(16,4),
    custo_seguro_rs_mes numeric(16,4),
    custo_ipva_rs_mes numeric(16,4),
    custo_licenciamento_rs_mes numeric(16,4),
    custo_lavagem_rs_mes numeric(16,4),
    custo_celular_rs_mes numeric(16,4),
    custo_outros_fixos_rs_mes numeric(16,4),
    custo_depreciacao_rs_mes numeric(16,4),
    custo_aluguel_rs_mes numeric(16,4),
    custo_total_economico_rs_mes numeric(16,4),
    resultado_economico_rs_mes numeric(16,4),
    custo_total_rs_km numeric(16,6),
    receita_equilibrio_rs_km numeric(16,6),
    receita_equilibrio_rs_hora numeric(16,6),
    status text NOT NULL CHECK (status IN ('COMPLETO_CENARIO','PARCIAL_PENDENTE')),
    campos_pendentes text,
    origem_consumo text NOT NULL,
    fonte_premissas text,
    observacoes text,
    atualizado_em timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (perfil_id, inmetro_id, modalidade)
);
CREATE INDEX IF NOT EXISTS fato_cenarios_motorista_modelo_idx
    ON analytics.fato_cenarios_motorista (marca_inmetro, modelo_inmetro, tecnologia);
COMMENT ON TABLE analytics.fato_cenarios_motorista IS
    'Simulações por versão INMETRO e perfil; NÃO são versões FIPE homologadas e não representam lucro observado.';
