-- PI06 / 005 — views analíticas para o backend. NÃO importa CSV automaticamente.
-- PRÉ-REQUISITOS: aplicar db/001, 002, 003 e 004 e popular as tabelas de base.
-- Correspondência com os CSVs exportados por gerar_cenarios_analiticos.py.
-- Importante: NÃO cruzar geografia OD com versão/receita de motorista.
BEGIN;
CREATE SCHEMA IF NOT EXISTS analytics;

-- Cadastro de hipóteses explícitas de receita (valor recebido após taxas da plataforma,
-- antes de despesas do motorista). Carregar dados_config/cenarios_receita_analitica.csv
-- via ETL seguro; a migration não insere números hipotéticos.
CREATE TABLE IF NOT EXISTS analytics.premissas_receita (
    cenario_receita_id TEXT PRIMARY KEY,
    titulo TEXT NOT NULL,
    receita_apos_plataforma_rs_mes NUMERIC(15,2) NOT NULL CHECK (receita_apos_plataforma_rs_mes >= 0),
    fonte TEXT NOT NULL CHECK (fonte = 'HIPOTESE_DIDATICA_NAO_OBSERVADA'),
    observacao TEXT NOT NULL
);

CREATE OR REPLACE VIEW analytics.v_painel_od_zonas AS
SELECT z.zona_od_id, z.zona_nome, z.municipio_od_id, z.municipio_nome,
       z.distrito_od_id, z.distrito_nome, z.escopo,
       z.origens_amostra AS viagens_origem_amostra,
       z.origens_expandidas AS viagens_origem_expandidas,
       z.destinos_amostra AS viagens_destino_amostra,
       z.destinos_expandidos AS viagens_destino_expandidas,
       z.tem_amostra_origem, z.tem_amostra_destino, z.geom,
       'METRO_OD_2023_MODOPRIN_12'::TEXT AS fonte,
       'AMOSTRAL_EXPANDIDO'::TEXT AS natureza_dado
FROM analytics.od2023_indicadores_zona z;


CREATE OR REPLACE VIEW analytics.v_painel_od_municipios AS
SELECT municipio_od_id, municipio_nome, COUNT(*)::INTEGER AS qtd_zonas,
       COUNT(*) FILTER (WHERE tem_amostra_origem)::INTEGER AS zonas_com_amostra_origem,
       COUNT(*) FILTER (WHERE tem_amostra_destino)::INTEGER AS zonas_com_amostra_destino,
       SUM(viagens_origem_amostra) AS viagens_origem_amostra,
       SUM(viagens_origem_expandidas) AS viagens_origem_expandidas,
       SUM(viagens_destino_amostra) AS viagens_destino_amostra,
       SUM(viagens_destino_expandidas) AS viagens_destino_expandidas,
       'METRO_OD_2023_MODOPRIN_12'::TEXT AS fonte,
       'AMOSTRAL_EXPANDIDO'::TEXT AS natureza_dado
FROM analytics.v_painel_od_zonas
GROUP BY municipio_od_id,municipio_nome;

CREATE OR REPLACE VIEW analytics.v_painel_od_distritos_capital AS
SELECT distrito_od_id, distrito_nome, COUNT(*)::INTEGER AS qtd_zonas,
       COUNT(*) FILTER (WHERE tem_amostra_origem)::INTEGER AS zonas_com_amostra_origem,
       COUNT(*) FILTER (WHERE tem_amostra_destino)::INTEGER AS zonas_com_amostra_destino,
       SUM(viagens_origem_amostra) AS viagens_origem_amostra,
       SUM(viagens_origem_expandidas) AS viagens_origem_expandidas,
       SUM(viagens_destino_amostra) AS viagens_destino_amostra,
       SUM(viagens_destino_expandidas) AS viagens_destino_expandidas,
       'METRO_OD_2023_MODOPRIN_12'::TEXT AS fonte,
       'AMOSTRAL_EXPANDIDO'::TEXT AS natureza_dado
FROM analytics.v_painel_od_zonas
WHERE municipio_od_id=36
GROUP BY distrito_od_id,distrito_nome;

CREATE OR REPLACE VIEW analytics.v_painel_od_top_destinos AS
WITH ranking AS (
    SELECT f.zona_origem_id, f.zona_destino_id, f.faixa_horaria,
           f.viagens_amostra, f.viagens_expandidas,
           f.duracao_media_ponderada_min,
           f.distancia_linha_reta_media_ponderada_km,
           ROW_NUMBER() OVER (
               PARTITION BY f.zona_origem_id, f.faixa_horaria
               ORDER BY f.viagens_expandidas DESC, f.zona_destino_id
           ) AS posicao
    FROM fato.od2023_fluxos_zona_faixa f
)
SELECT r.*, z.zona_nome AS nome_zona_destino, z.municipio_nome AS municipio_destino,
       'METRO_OD_2023_MODOPRIN_12'::TEXT AS fonte,
       'AMOSTRAL_EXPANDIDO'::TEXT AS natureza_dado
FROM ranking r
JOIN geo.zonas_od2023 z ON z.zona_od_id=r.zona_destino_id
WHERE r.posicao <= 5;

CREATE OR REPLACE VIEW analytics.v_energia_inmetro AS
SELECT e.inmetro_id, e.marca_inmetro, e.modelo_inmetro, e.versao_inmetro,
       e.tecnologia, e.modalidade,
       e.custo_energia_rs_km, e.km_mes_hipotese,
       ROUND(e.custo_energia_rs_km * e.km_mes_hipotese, 2) AS custo_energia_rs_mes_hipotetico,
       CASE WHEN LOWER(e.tecnologia) LIKE '%hibrid%' THEN 'Híbrido'
            WHEN LOWER(e.tecnologia) LIKE '%eletric%' OR LOWER(e.tecnologia) LIKE '%elétric%' THEN 'Elétrico'
            WHEN LOWER(e.tecnologia) LIKE '%combust%' THEN 'Gasolina'
            ELSE 'Não classificado' END AS grupo_interface,
       'INMETRO_PBEV+ANP_2026+ANEEL_2026'::TEXT AS fonte,
       'SIMULADO_ENERGIA'::TEXT AS natureza_dado
FROM pi06_staging.cenarios_inmetro_energia e;

-- Subtotal = SOMENTE custos identificados. Não é custo total se houver NULL.
-- Dependendo dos dados, há campos específicos que são zero por estrutura
-- (por exemplo, depreciação no aluguel), mas NULL significa DESCONHECIDO.
CREATE OR REPLACE VIEW analytics.v_motorista_custos AS
SELECT m.*,
       c.componentes_custos_informados,
       11-c.componentes_custos_informados AS componentes_custos_pendentes,
       c.subtotal_custos_conhecidos_rs_mes,
       (c.componentes_custos_informados=11) AS todos_custos_preenchidos,
       'ECONOMIA_COMPLETA_PI06_INMETRO'::TEXT AS fonte,
       'SIMULADO_COM_PREMISSAS'::TEXT AS natureza_dado
FROM analytics.fato_cenarios_motorista m
CROSS JOIN LATERAL (
    SELECT COUNT(custo)::INTEGER AS componentes_custos_informados,
           SUM(custo) AS subtotal_custos_conhecidos_rs_mes
    FROM (VALUES
        (m.custo_energia_rs_mes),
        (m.custo_manutencao_rs_mes),
        (m.custo_pneus_rs_mes),
        (m.custo_seguro_rs_mes),
        (m.custo_ipva_rs_mes),
        (m.custo_licenciamento_rs_mes),
        (m.custo_lavagem_rs_mes),
        (m.custo_celular_rs_mes),
        (m.custo_outros_fixos_rs_mes),
        (m.custo_depreciacao_rs_mes),
        (m.custo_aluguel_rs_mes)
    ) AS componentes(custo)
) c;

CREATE OR REPLACE VIEW analytics.v_sensibilidade_receita AS
SELECT m.perfil_id, m.regime, m.inmetro_id, m.modalidade, m.tecnologia,
       p.cenario_receita_id,
       p.receita_apos_plataforma_rs_mes,
       m.custo_total_economico_rs_mes,
       c.subtotal_custos_conhecidos_rs_mes,
       c.componentes_custos_pendentes,
       CASE WHEN c.componentes_custos_pendentes=0 AND m.custo_total_economico_rs_mes IS NOT NULL
            THEN p.receita_apos_plataforma_rs_mes-m.custo_total_economico_rs_mes
            ELSE NULL END AS resultado_economico_simulado_rs_mes,
       CASE WHEN c.componentes_custos_pendentes=0 AND m.custo_total_economico_rs_mes IS NOT NULL
            THEN (p.receita_apos_plataforma_rs_mes-m.custo_total_economico_rs_mes)/NULLIF(m.km_mes,0)
            ELSE NULL END AS resultado_simulado_rs_km,
       CASE WHEN c.componentes_custos_pendentes=0 AND m.custo_total_economico_rs_mes IS NOT NULL
            THEN 'RESULTADO_SOMENTE_COM_HIPOTESE_DE_RECEITA'
            ELSE 'CUSTOS_INCOMPLETOS_SEM_RESULTADO' END AS situacao_calculo,
       'SIMULACAO_HIPOTETICA'::TEXT AS natureza_dado
FROM analytics.fato_cenarios_motorista m
JOIN analytics.v_motorista_custos c
  ON c.perfil_id=m.perfil_id AND c.inmetro_id=m.inmetro_id AND c.modalidade=m.modalidade
CROSS JOIN analytics.premissas_receita p;

COMMENT ON VIEW analytics.v_painel_od_zonas IS
  'OD 2023, modo 12, amostra expandida. Não são viagens exclusivas Uber; sem amostra fica NULL.';
COMMENT ON VIEW analytics.v_energia_inmetro IS
  'Custos energéticos por versão INMETRO sem homologação automática FIPE.';
COMMENT ON VIEW analytics.v_motorista_custos IS
  'Subtotal conhecido não é total, e custos/receitas podem estar incompletos.';
COMMENT ON VIEW analytics.v_sensibilidade_receita IS
  'Receitas ilustrativas depois das taxas da plataforma, antes das despesas. Não é renda observada nem lucro territorial.';
COMMIT;
