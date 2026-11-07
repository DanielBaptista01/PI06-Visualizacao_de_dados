# PI06 — Tabelas-mestras específicas por domínio

Gerado em UTC: 2026-11-07T15:07:23.143182+00:00

## Política de modelagem
- Uma tabela por entidade, evento ou granularidade verificável; nenhuma tabela gigante.
- Todos os CSVs de entrada em dados_padronizados permanecem sem alterações.
- Zero não substitui ND/ausente; saídas mantêm colunas originais.
- `id_registro_mestre` identifica somente a linha da respectiva fonte/versão. Não representa identidade universal de veículo.
- `linha_csv_origem` permite rastrear a posição no arquivo, considerando cabeçalho na linha 1.
- Tabelas de escopo nacional, estadual, municipal e pontual não são propagadas para Zonas OD sem vínculo validado.

## Catálogo de domínios
- `territorios/dim_municipios_sp.csv` — 645 linhas; um município IBGE SP
- `veiculos/dim_modelos_versoes_inmetro.csv` — 968 linhas; linha da planilha organizada INMETRO
- `veiculos/fato_cotacoes_fipe_parcial.csv` — 489 linhas; versão FIPE × ano-modelo × mês de referência
- `uber/regra_modelos_uber.csv` — 1219 linhas; marca × modelo e critérios de ano mínimo por categoria
- `uber/fato_ofertas_locacao_uber.csv` — 56 linhas; oferta comercial individual
- `recarga/dim_pontos_recarga_ocm.csv` — 143 linhas; ponto cadastrado com localização
- `recarga/fato_totais_recarga_abve_municipios.csv` — 32 linhas; agregado por município ABVE (não pontos OCM)
- `recarga/fato_serie_recarga_abve.csv` — 17 linhas; ano × mês da evolução declarada
- `mobilidade/fato_viagens_aplicativo_od2023.csv` — 4229 linhas; registro amostral de viagem; peso FE_VIA
- `energia/fato_pesquisas_precos_anp_sp.csv` — 14920 linhas; observação de preço de revenda/produto/data
- `energia/fato_tarifas_aneel_nacional.csv` — 332165 linhas; distribuidora × vigência × modalidade × posto × unidade
- `frota/fato_frota_senatran_ano.csv` — 91563 linhas; frota por município/ano e demais dimensões
- `frota/fato_frota_senatran_cep.csv` — 9164 linhas; frota por município/CEP e demais dimensões
- `frota/fato_frota_senatran_combustivel.csv` — 2540 linhas; frota por município/combustível
- `frota/fato_frota_senatran_marca_modelo.csv` — 81652 linhas; frota por município/marca-modelo
- `frota/fato_frota_senatran_potencia.csv` — 77770 linhas; frota por município/potência
- `frota/fato_frota_senatran_tipo.csv` — 646 linhas; frota municipal por tipos em colunas
- `mercado/fato_vendas_abve_rmsp.csv` — 33 linhas; agregado de vendas por município RMSP
- `mercado/fato_vendas_abve_capital.csv` — 1 linhas; agregado de vendas municipal da capital; visão sobreposta à RMSP
- `mercado/fato_vendas_abve_modelos.csv` — 1912 linhas; ano × mês × fabricante × modelo
- `mercado/fato_vendas_mhev_brasil.csv` — 499 linhas; vendas MHEV por município no recorte Brasil
- `mercado/fato_vendas_mhev_rmsp.csv` — 31 linhas; vendas MHEV por município RMSP
- `mercado/fato_vendas_mhev_capital.csv` — 1 linhas; vendas MHEV municipal da capital; visão sobreposta
- `mercado/fato_serie_abve_tecnologia.csv` — 197 linhas; ano × mês × tecnologia (quantidade/share de significado misto)
- `relacionamentos/ponte_candidatos_uber_inmetro.csv` — 485 linhas; candidatos ou cobertura por linha de modelo Uber
- `relacionamentos/ponte_candidatos_uber_fipe.csv` — 2 linhas; candidatos ou cobertura por linha de modelo Uber
- `relacionamentos/cobertura_modelos_uber.csv` — 1219 linhas; candidatos ou cobertura por linha de modelo Uber

## Alertas e limites de integração
- Uber: sufixo HTML "Down" removido APENAS em marca_comparacao; marca original mantida.
- ANEEL: preservada sem interpretação semântica completa. Dimensões não identificadas automaticamente: ['unidade']. Colunas disponíveis: ['DatGeracaoConjuntoDados', 'DscREH', 'SigAgente', 'NumCNPJDistribuidora', 'DatInicioVigencia', 'DatFimVigencia', 'DscBaseTarifaria', 'DscSubGrupo', 'DscModalidadeTarifaria', 'DscClasse', 'DscSubClasse', 'DscDetalhe', 'NomPostoTarifario', 'DscUnidadeTerciaria', 'SigAgenteAcessante', 'VlrTUSD', 'VlrTE', 'te_num', 'tusd_num']. Não usar em cálculo econômico até conferir o esquema oficial.
- Vínculos municipais com status nao_encontrado_no_ibge_sp: 1 linhas (não ligados automaticamente).
- Vínculos municipais com status fora_do_escopo_sp_ou_uf_incerta: 359 linhas (não ligados automaticamente).
- A origem IBGE RMSP marca pertença ao conjunto de 39 municípios, não gera zonas OD.
- As pontes Uber-INMETRO e Uber-FIPE são candidatas somente por marca/modelo EXATO normalizado; NÃO comprovam versão, ano ou categoria elegível.
- A FIPE é parcial; ausência de candidato NÃO significa ausência de preço na tabela FIPE completa.
- Os dados SENATRAN são fatos distintos por dimensão, não somar suas tabelas entre si.
- ABVE capital está contida em recortes mais amplos; não somar vistas capital + RMSP + Brasil.
- ANEEL nacional tem vigências/unidades distintas (R$/kW e R$/kWh); não calcular custo por kWh ainda.
- OD registra amostras expandidas por FE_VIA; distância pode ser em linha reta e não percurso real.
- Recarga OCM (pontos) não equivale à quantidade agregada de carregadores da ABVE.
- Sem tabelas de fotos/imagens de eletropostos: nenhuma fonte de fotos validada foi fornecida.
- Para georreferenciar Zonas OD é preciso cruzamento espacial com a geometria oficial de zonas OD; não imputar zonas por nome de município.

## Próximas ações
1. Revisar `relacionamentos/cobertura_modelos_uber.csv` e as pontes; não converter candidatos em confirmações automaticamente.
2. Incorporar malha das Zonas OD para relações espaciais com pontos de recarga.
3. Pesquisar lacunas da etapa 1.9 usando `relatorios/lacunas_variaveis.csv`.
4. Publicar dimensões e fatos no PostgreSQL/PostGIS apenas após aprovar chaves e cargas.
