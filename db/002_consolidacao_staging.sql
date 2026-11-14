-- PI06: estrutura de staging para importação posterior dos CSVs consolidados.
-- Não executa carga automaticamente nem altera schemas existentes fora de pi06_staging.
CREATE SCHEMA IF NOT EXISTS pi06_staging;
CREATE TABLE IF NOT EXISTS pi06_staging.veiculos_fipe (
  veiculo_id text PRIMARY KEY,
  marca_fipe text NOT NULL,
  modelo_fipe text NOT NULL,
  ano_modelo text,
  combustivel_fipe text,
  preco_fipe_rs numeric(15,2),
  referencia_fipe text,
  categorias_ano_compativel text,
  quantidade_candidatos_inmetro_familia integer,
  quantidade_candidatos_propulsao_compativel integer,
  status_consumo text NOT NULL,
  consumo_inmetro_id_aprovado text,
  custo_energia_rs_km_atribuido numeric(14,6),
  status_calculo text
);
CREATE TABLE IF NOT EXISTS pi06_staging.fipe_inmetro_candidatos (
  veiculo_id text NOT NULL,
  inmetro_id text NOT NULL,
  marca_fipe text,
  modelo_fipe text,
  ano_modelo text,
  combustivel_fipe text,
  modelo_inmetro text,
  versao_inmetro text,
  tecnologia_inmetro text,
  propulsao_compativel_preliminar boolean,
  status_match text NOT NULL,
  consumo_atribuido_fipe boolean NOT NULL DEFAULT FALSE,
  evidencia_validacao text,
  PRIMARY KEY (veiculo_id,inmetro_id)
);
CREATE TABLE IF NOT EXISTS pi06_staging.uber_ano_candidatos (
  veiculo_id text NOT NULL,
  categoria_uber text NOT NULL,
  modelo_uber text NOT NULL,
  ano_min_lista integer,
  status_ano text NOT NULL,
  elegibilidade_confirmada boolean NOT NULL DEFAULT FALSE,
  PRIMARY KEY(veiculo_id,categoria_uber,modelo_uber)
);
-- Cenários regulatórios INMETRO (não constituem custos homologados FIPE).
CREATE TABLE IF NOT EXISTS pi06_staging.cenarios_inmetro_energia (
  inmetro_id text NOT NULL,
  marca_inmetro text,
  modelo_inmetro text,
  versao_inmetro text,
  tecnologia text,
  km_mes_hipotese numeric(10,2),
  eficiencia_recarga_hipotese numeric(7,4),
  origem_consumo text,
  tipo_calculo text,
  tarifa_eletrica_inclui_tributos boolean,
  modalidade text NOT NULL,
  consumo_original numeric(12,5),
  unidade_consumo_original text,
  custo_energia_rs_km numeric(14,6),
  custo_energia_rs_mes numeric(16,2),
  observacoes text,
  PRIMARY KEY (inmetro_id, modalidade)
);
COMMENT ON SCHEMA pi06_staging IS 'CSV provisórios: vínculos não homologados e cenários energéticos; não publicar como lucro observado';
