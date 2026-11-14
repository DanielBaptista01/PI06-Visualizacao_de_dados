# Inventário técnico e baseline PI06

**Revisado em 14/11/2026** a partir do repositório `DanielBaptista01/PI06-Visualizacao_de_dados`, commit `9337f69347718e04117fcf526e1b931db5e26a6f`, e dos resultados de execução fornecidos pela equipe. Não é inventário dos objetos atualmente existentes no Storage; esse inventário deve ser conciliado separadamente por caminho e SHA-256.

## Resumo do versionamento

- 185 arquivos rastreados pela `main` naquele commit; conteúdo de aproximadamente 404,8 MiB (não é tamanho do `.git` com histórico).
- `dados_mestres/`: 147,0 MiB; `dados_padronizados/`: 121,0 MiB; `dados_limpos/`: 117,5 MiB.
- A ANEEL nacional em três camadas (`dados_limpos/02_ANEEL_NACIONAL.csv`, `dados_padronizados/02_ANEEL_NACIONAL.csv` e `dados_mestres/.../fato_tarifas_aneel_nacional.csv`) ocupa cerca de 251 MiB, **mas não são arquivos byte a byte idênticos**.
- `dados_mestres/atual.json` aponta para `execucoes/20261107T150640Z_fd637316`; preservar a integridade dessa referência até definir reidratação por Storage.

## Matriz de fontes e dados

| Fonte | Granularidade / recorte | Referência em análise | Artefatos usados | Qualidade / cuidado |
| --- | --- | --- | --- | --- |
| FIPE (API Parallelum) | Versão × ano-modelo × mês | novembro/2026 | `dados_limpos/08_FIPE_VEICULOS_PARCIAL.csv`; checkpoints fora do Git | 1.903 / 6.954 combinações catalogadas (27,37%); não é universo completo; ano zero km pode vir vazio |
| INMETRO (PBEV) | Marca × modelo × versão; campos de combustíveis/eletricidade | tabela do projeto validada em nov/2026 | `dados_limpos/05_INMETRO_VALIDADO.csv`; `05_INMETRO_ORGANIZADO.csv` | 968 registros, incluindo combustão, híbridos, plug-in e elétricos; comparar versão e unidade de medida |
| Uber / Uber Match | Regras por modelo/categoria e oferta de locação individual | snapshot 2026 | `09_UBER_MODELOS_SP.csv`; `17_UBER_MATCH_OFERTAS_SP.csv` | Ano mínimo não é elegibilidade completa; preço/seguro variam por contrato e data |
| ANP | Revenda de combustível por produto, posto, município e semana | semana 08–14/11/2026 | `03_ANP_SP_NOV2026.csv`, `03_ANP_PRECOS_MUNICIPIOS_NOV2026.csv`, `03_ANP_PRECOS_CAPITAL_NOV2026.csv` | SP capital: gasolina comum R$ 6,342190/l; etanol R$ 4,089952/l nessa referência; média amostral semanal |
| ANEEL / Enel SP | Distribuidora, grupo tarifário, vigência e bandeira | 2026-07-04 a 2027-07-03; bandeira nov/2026 | `02_ANEEL_ENEL_SP_RESIDENCIAL.csv`, `02_ANEEL_CENARIO_ENERGIA_SP.csv` | R$ 0,78938/kWh antes de tributos; não representa tarifa pública de recarga |
| SENATRAN | Frota por município e **cada dimensão publicada separadamente** | set/2026, marca/modelo jul/2026 | `06_SENATRAN_*_SP.csv` | Frota total ou de automóveis não implica frota da Uber; não juntar fatos de granularidades distintas sem chave adequada |
| IPVA SP | Base venal por veículo/regra fiscal | exercício 2026 | `dados_padronizados/18_IPVA_SP_VALORES_VENAIS_2026.csv`; `dados_complementares/ipva_sp_2026/` | Não aplicar alíquota genericamente sem checar isenção e correspondência com veículo; FIPE nov/2026 ≠ base venal 2026 |
| IBGE | Município / código territorial | material disponível no projeto | `04_IBGE_RMSP.csv`, `04_IBGE_SP.csv`, GeoJSON | Chaves IBGE ≠ código de município da OD |
| OD 2023 (Metrô) | Viagem amostral `MODOPRIN=12`; zona × faixa e fluxo origem-destino | pesquisa 2023, anexos publicados em 2025 | `07_ORIGEM_DESTINO.csv`; `dados_referencia_od/`; GeoJSONs gerados em `dados_relatorios/territorio_od2023/` | 4.229 registros, expansão total 1.041.875,01; 527 zonas, 39 municípios, 343 zonas SP; distância em linha reta |
| Open Charge Map | Ponto cadastrado com lat/long | snapshot API disponível no projeto | `10_OPEN_CHARGE_MAP_SP.csv` | Cadastro de ponto não é garantia de funcionamento ou preço real; pode permitir join espacial validado |
| ABVE | Vendas/mercado de veículos eletrificados e eletropostos | múltiplas referências publicadas | `11_*`, `14_*`, `15_*`, `16_*`, `17_ABVE_*` | Vendas e quantidade de pontos de recarga não são frota circulante ou demanda de aplicativo |

## Resultados derivados existentes

| Etapa | Código | Artefatos | Estado |
| --- | --- | --- | --- |
| Padronização | `padronizar_bases.py` | `dados_padronizados/` | Dados transformados; fonte do pipeline de tabelas-mestras por domínio |
| Master por domínio | `construir_tabelas_mestres.py` | `dados_mestres/execucoes/`, `dados_mestres/atual.json` | Snapshot de 07/11, avaliar reprocessamento com versões recentes |
| Consolidação candidata FIPE/Inmetro/Uber | `consolidar_pi06.py` | `dados_relatorios/consolidacao_integrada/{dim_veiculos_fipe,bridge_fipe_inmetro_pendente,bridge_fipe_uber_ano,fato_cenarios_inmetro_energia}.csv` | 1.903 FIPE; 1.284 com candidato INMETRO; 1.706 com ano Uber; 838 simulações INMETRO; 0 homologados automaticamente |
| Cálculo econômico | `economia_completa_pi06.py` | `dados_relatorios/economia_completa/fato_cenarios_motorista.csv` | 1.676 cenários, todos `PARCIAL_PENDENTE` na primeira execução |
| Pesquisa econômica | `integrar_pesquisa_economica.py`, `consolidar_variaveis_19.py` | `catalogo_premissas_economicas.csv`, `dados_config/`, `dados_complementares/etapa19/` | Mistura explícita de fontes oficiais, referências de mercado e hipóteses |
| OD estatística/territorial | `integrar_od2023.py` | `dados_relatorios/territorio_od2023/` com 13 artefatos | 527 zonas e 39 municípios; 1145 grupos origens, 1143 destinos, 3383 fluxos; GeoJSONs preparados |
| Geografia adicional | `integrar_geografia_od.py` | `dados_geograficos/execucoes/` | Recortes administrativos/pontos OCM adicionais; não substituir diretamente pelo novo ETL OD |

## Qualidade geográfica e controle de tempo

- `MODOPRIN=12` significa **táxi não convencional / aplicativo**, não exclusivamente Uber.
- `FE_VIA` expande viagens, não pessoas ou motoristas; `DISTANCIA` é em metros em linha reta.
- Na última execução, havia amostra em 466 zonas de origem e 468 de destino; zonas sem observação não recebem zero verdadeiro.
- O SHP da OD gerou 527 polígonos; 196 estavam originalmente inválidos, com um reparo adicional após reprojeção, e nenhuma diferença de área acima de 5% na auditoria. Recomenda-se validação visual antes de publicar.
- A correspondência das zonas registra a anomalia da zona 485 corrigida de código municipal `80` para `20` (Juquitiba), preservando a origem da correção.
- OD 2023 e preços de energia de novembro/2026 **não são observações do mesmo período**; cruzar apenas em simulações hipotéticas identificadas.

## Hierarquia de evidências e política de ausência

1. **Observado:** valores da fonte com referência temporal e granularidade explicitadas.
2. **Derivado:** cálculo a partir de observados, com fórmula e unidades.
3. **Simulado:** hipótese de uso, contrato, renda, preço/tarifa ou parâmetro de desempenho.
4. **Pendente:** ausente ou sem correspondência segura; `NULL`, nunca preencher com zero.

Manter `metadata.coletas`/manifestos com fonte, data, SHA-256, quantidade e limitações. Preços de 2026 não devem ser apresentados como valores medidos no ano da OD 2023.

## Verificação para retirada de CSVs do Git

Antes de `git rm --cached` confirmar: (a) fonte RAW e/ou snapshot tratado imutável no Storage, (b) SHA-256 coincidente, (c) manifesto com o caminho, (d) mecanismo de recuperação ou reprocessamento usado pelo código, e (e) validação por outro clone/usuário. **`.gitignore` não elimina arquivos já versionados**; retirar do Git não elimina histórico anterior nem cria backup.

Fontes para consulta: `docs/ARQUITETURA_DADOS.md`, `docs/OD2023_METODOLOGIA.md`, URLs nos catálogos das próprias fontes e `dados_referencia_od/manifesto_fontes_dimensoes.json`.
