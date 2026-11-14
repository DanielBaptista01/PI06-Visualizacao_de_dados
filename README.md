# PI06 — Visualização de Dados

**Análise de custos de veículos e deslocamentos por aplicativo na Região Metropolitana de São Paulo (RMSP)**, com aprofundamento territorial no município de São Paulo. O produto final será uma narrativa interativa (*scrollytelling*) com mapa por município/distrito/zona OD e um comparador econômico de veículos a combustão/flex, híbridos e elétricos.

> **Situação em 14/11/2026:** ETL das principais fontes, tabelas-mestras provisórias, motor econômico parametrizado e integração OD 2023 executados. **Ainda não** são produto final nem dados de lucro observado: correspondências entre versões FIPE–INMETRO seguem sem homologação individual, cenários de receita/custos podem estar incompletos e carga operacional no PostGIS/backend ainda não foi confirmada.

## Onde está cada documento

| Documento | Assunto |
| --- | --- |
| [ROADMAP.md](ROADMAP.md) | Etapas concluídas, pendentes e próximos marcos |
| [docs/INVENTARIO_DADOS.md](docs/INVENTARIO_DADOS.md) | Arquivos, cobertura, fontes, temporalidade e granularidade |
| [docs/METODOLOGIA_ECONOMICA.md](docs/METODOLOGIA_ECONOMICA.md) | Fórmulas, premissas, classificação dos dados e limitações |
| [docs/OD2023_METODOLOGIA.md](docs/OD2023_METODOLOGIA.md) | Tratamento da OD 2023 e geometrias |
| [docs/CENARIOS_ANALITICOS_E_BACKEND.md](docs/CENARIOS_ANALITICOS_E_BACKEND.md) | Indicadores, dimensões, joins válidos e contrato para o backend |
| [docs/PLANO_ORGANIZACAO_REPOSITORIO.md](docs/PLANO_ORGANIZACAO_REPOSITORIO.md) | Arquivos a manter, dependências e migração para Storage |
| [docs/ARQUITETURA_DADOS.md](docs/ARQUITETURA_DADOS.md) | GitHub, Supabase Storage e PostGIS |
| [docs/NAVEGACAO_MAPA_E_BACKEND.md](docs/NAVEGACAO_MAPA_E_BACKEND.md) | Navegação territorial proposta |

## Fontes e recortes

- **ANP:** preço de gasolina e etanol; referência local novembro/2026, com data semanal identificada.
- **ANEEL:** tarifa da Enel SP e bandeira; tarifa base **sem tributos** no cenário atual.
- **INMETRO/PBEV:** consumo e versão de veículos; preservar a tecnologia e a unidade física.
- **FIPE:** valores por marca, modelo, versão e ano; catálogo **parcial** em novembro/2026.
- **Uber:** regras de categorias/ano e ofertas Uber Match; associação por nome/ano é **candidata**, não elegibilidade definitiva.
- **SENATRAN:** frota; diferentes arquivos possuem diferentes granularidades e não identificam veículos efetivamente usados pela Uber.
- **OD 2023, Metrô:** viagens com `MODOPRIN=12` (táxi não convencional/aplicativo), peso `FE_VIA` e zonas. Não representa apenas Uber nem operação individual em 2026.
- **IBGE / dados territoriais / GeoSampa:** referência municipal e eventual cruzamento com divisões da Prefeitura; não equiparar códigos ou limites sem validação.
- **ABVE / Open Charge Map:** cenário de eletrificação e pontos de recarga, mantendo datas de levantamento e limitações de cobertura.

## Arquitetura

```text
RAW de fontes oficiais / páginas-snapshot ---> Object Storage S3 (imutável, SHA-256)
                                                |
                                          ETL Python
                                                |
                      dados_limpos -> dados_padronizados -> tabelas-mestras
                                                |
                                       PostgreSQL / PostGIS
                                           /          \
                                     analytics       metadata
                                           \          /
                                           API/backend
                                                |
                                    site com mapa + comparador
```

**GitHub guarda código, SQL, configuração de exemplo e documentação**; arquivos RAW e snapshots grandes devem ser mantidos em Storage, após comprovação de integridade e possibilidade de reprodução.

## Ambiente e instalação (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Configure `.env` localmente com credenciais do banco, Storage e serviços necessários. **Nunca versionar `.env`, chaves, tokens, cookies ou checkpoints privados.** Se usar `.venv-2`, ative esse ambiente em vez de criar outro.

## Fluxo atual do pipeline

Execute **somente a etapa desejada**. Alguns passos exigem acesso aos RAW e à API, e novas coletas podem alterar a referência temporal.

```powershell
# Extração/limpeza (RAW local ou Storage configurado)
python extrair.py bases

# Preparação das camadas por domínio
python padronizar_bases.py
python construir_tabelas_mestres.py --validar
python construir_tabelas_mestres.py

# Consolidação FIPE × INMETRO × Uber (candidatos, sem homologação)
python consolidar_pi06.py

# Modelo econômico por versão INMETRO e perfis existentes
python economia_completa_pi06.py

# Integração OD 2023, usando microdados tratados
python integrar_od2023.py --shape "ORIGEM_E_DESTINO_2023\002_SiteMetro Mapas_190225\Shape\Zonas_2023.shp" --sobrescrever
```

> `construir_tabela_mestra.py` é uma etapa de auditoria por veículo FIPE, diferente de `construir_tabelas_mestres.py` (camada por domínio). `integrar_geografia_od.py` agrega recortes e pontos geográficos adicionais, enquanto `integrar_od2023.py` gera dimensões e fatos de viagens. **Não excluir ou fundir scripts sem equivalência funcional testada.**

### Testes permanentes

```powershell
python -m unittest discover -v -p "test_*.py"
```

Os testes sintéticos não substituem validações com os arquivos reais. Consulte [docs/PLANO_ORGANIZACAO_REPOSITORIO.md](docs/PLANO_ORGANIZACAO_REPOSITORIO.md) antes de mover entradas do pipeline.

## Baseline de resultados reproduzidos pela equipe

| Camada | Resultado registrado | Ressalva |
| --- | --- | --- |
| FIPE | 1.903 registros válidos em novembro/2026 | Cobertura parcial de 6.954 combinações catalogadas (27,37%); não generalizar |
| Matching | 1.284 FIPE com candidato INMETRO; 1.706 com algum ano Uber compatível | 0 versões FIPE–INMETRO homologadas automaticamente |
| Simulação energética | 838 cenários por versão INMETRO e combustível/modalidade | Não vincular automaticamente a uma versão FIPE |
| Economia motorista | 1.676 linhas, 2 perfis; 0 completos na execução inicial | Receita, IPVA individual e outros parâmetros sem preenchimento completo |
| OD 2023 | 4.229 viagens amostrais modo 12; 1.041.875,01 viagens expandidas | Não são viagens Uber exclusivas |
| Territorial | 527 zonas, 39 municípios, 343 zonas na capital e 96 distritos | GeoJSONs gerados; revisão cartográfica visual antes de publicar |

## Banco e situação de publicação

Os SQLs versionados estão em `db/001_init.sql` até `db/004_od2023_territorio.sql`. Eles **definem estruturas**, mas não comprovam carga de dados. Rodar `python database_utils.py init` aplica apenas o DDL inicial segundo a implementação atual. A importação das tabelas, criação de views analíticas e endpoints continuam pendentes.

```powershell
python infra_check.py
```

## O que falta

1. **Higiene/arquitetura:** validar Storage e remover do Git os grandes CSVs reproduzíveis sem quebrar as dependências; manter os tests e manifests.
2. **Documentação e cenários:** congelar baseline, montar visões analíticas separadas para mobilidade territorial e economia por veículo, com parametrização da receita e todos os estados de qualidade.
3. **Backend:** carregar dimensões/fatos no PostGIS, disponibilizar consultas/GeoJSON, paginação, filtros e políticas de acesso.
4. **Frontend:** mapa RMSP → município → distrito/zona, indicadores OD 2023 e comparador econômico; preservar a diferença entre dados históricos, referências e simulações.

Veja [ROADMAP.md](ROADMAP.md) para os critérios de conclusão de cada etapa.
