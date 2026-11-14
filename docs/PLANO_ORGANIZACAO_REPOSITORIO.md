# Plano de organização e redução de dados rastreados — PI06

**Estado auditado:** branch `main`, commit `9337f69347718e04117fcf526e1b931db5e26a6f` de 14/11/2026. Resultado: **185 arquivos**, aproximadamente **404,8 MiB** de conteúdo versionado. O commit anterior tinha 230 arquivos; já foram retirados **45**. A árvore está limpa de `dados_backups/`, de scripts `_backup.py`, de `modelos_carros_uber_files/` e de duplicações conhecidas dos testes.

Este documento é **um plano**, não confirmação de arquivos apagados ou enviados ao Storage. Evitar executar remoções antes de garantir que outro membro da equipe recupera as bases.

## Decisão por pasta

| Caminho | Situação/decisão | Pré-condição para mudança |
| --- | --- | --- |
| `dados_referencia_od/` | **MANTER no Git**: quatro pequenos arquivos de dimensões/manifesto territorial, usados em testes | Nenhuma |
| `dados_config/` | **MANTER no Git**: perfis e parâmetros nomeados; não incluem segredos | Revisar a validade das premissas ao recalcular |
| `db/` | **MANTER no Git**. Migrations `001` a `004` já estão organizadas na mesma pasta | Criar futuras migrações `005+`, sem renumerar existentes |
| `docs/`, `README.md`, `ROADMAP.md` | **MANTER e atualizar** | Commit documental específico |
| `.env.example`, `.gitignore`, `requirements.txt` | **MANTER** | Nunca adicionar `.env` ou dados sensíveis |
| `test_*.py` (raiz) | **MANTER**, pois comprovam regressões após refatoração | Migrar para `tests/` somente ajustando imports e CI |
| `dados_limpos/` | **MANTER operacional por enquanto** | ETL lê caminhos fixos; retirar do Git só após Storage + rotina de restauração verificados |
| `dados_padronizados/` | **MANTER operacional por enquanto** | `construir_tabelas_mestres.py` depende desses CSVs; criar pipeline de reconstrução primeiro |
| `dados_mestres/execucoes/` | **CANDIDATA A STORAGE**, não apagar do computador | `dados_mestres/atual.json` aponta para `20261107T150640Z_fd637316`; sem restauração esse ponteiro quebra |
| `dados_mestres/atual.json` | **MANTER provisoriamente**, porém atualizar política de apontamento | Nunca publicar um JSON cujo destino não é recuperável |
| `dados_geograficos/execucoes/` | **CANDIDATA A STORAGE/POSTGIS** | Manter auditorias e manifestos da publicação; preservar versão cartográfica original |
| `dados_complementares/` | **MANTER** catálogos pequenos e referências, **MIGRAR** snapshot grande do IPVA para Storage se recuperável | Usos de IPVA e origem exata validados |
| `dados_analiticos/modelo_economico/` | **MANTER como exemplo/snapshot leve** ou trocar por consulta ao banco posteriormente | Não tratar outputs antigos como dados atuais |
| `INMETRO-dados-brutos/`, `INMETRO-dados-organizados/` | **MOVER RAW/ORGANIZADO para Storage**, depois `git rm --cached` | Conferir checksum e reprocessamento; apesar de `.gitignore`, permanecem rastreados atualmente |
| `sincronizacao/sincronizacao.md` | **MANTER documentação da sincronização** | Ajustar instruções quando processo de Storage mudar |

## Scripts — o que NÃO excluir apesar da semelhança de nomes

| Scripts | Responsabilidades distintas atualmente |
| --- | --- |
| `construir_tabelas_mestres.py` versus `construir_tabela_mestra.py` | O primeiro publica tabelas por domínio a partir de `dados_padronizados`; o segundo propõe vínculos candidatos por FIPE, Uber e INMETRO |
| `consolidar_pi06.py` | Consolida candidates FIPE/INMETRO/Uber e gera energia por INMETRO; não representa substituição total dos dois anteriores |
| `integrar_od2023.py` versus `integrar_geografia_od.py` | O primeiro agrega viagens/zonas e GeoJSONs; o segundo integra distritos/regiões/eletropostos e joins territoriais adicionais |
| `modelo_economico.py` versus `economia_completa_pi06.py` | O primeiro contém cálculo energético/cenários; o segundo agrega custos fixos, aluguel e receita ao cenário INMETRO |
| `consolidar_variaveis_19.py`, `preencher_pesquisas_19.py`, `integrar_pesquisa_economica.py` | Etapas complementares de catalogação econômica; há sobreposição, mas remover só após checar qualidade e origem das informações |
| `extrair_bases.py`, `extrair.py`, `extrair_fipe.py`, `pipeline_uber_fipe.py` | Há extração, orquestração, incremental FIPE e regras de auditoria; não unir por semelhança de nome |

**Sugestão de estrutura futura, não obrigação imediata:**

```text
src/pi06/ingestao/       extrair_bases, extrair_fipe, extrair_apis, extrair_uber_match
src/pi06/tratamento/     padronizar_bases, pipeline_utils
src/pi06/mestres/       construir_tabelas_mestres, consolidar_pi06, validacoes
src/pi06/economia/      modelo_economico, economia_completa_pi06, pesquisa
src/pi06/territorio/    integrar_od2023, integrar_geografia_od
src/pi06/infra/         database_utils, storage_utils, migrar_raw

tests/                   testes permanentes
scripts/                 CLIs/entrypoints compatíveis com os comandos atuais
db/                      migrações 001..004, novas migrações futuras
docs/                    metodologia, fontes e contratos
dados_config/            perfis e parâmetros versionados
dados_referencia_od/     dimensões e manifesto canônico
```

**Não executar esta movimentação antes dos testes e da atualização dos imports.** Mover imediatamente scripts da raiz quebraria `python extrair.py` e invocações atuais.

## Prioridades de redução de volume

1. `dados_limpos/02_ANEEL_NACIONAL.csv` (76,8 MiB), `dados_padronizados/02_ANEEL_NACIONAL.csv` (80,5 MiB) e `dados_mestres/execucoes/.../energia/fato_tarifas_aneel_nacional.csv` (93,6 MiB): ~251 MiB somados. **Não são arquivos idênticos**: são camadas diferentes de uma mesma fonte.
2. Demais CSVs grandes de SENATRAN entre `dados_limpos/`, `dados_padronizados/` e `dados_mestres/`: camadas válidas que não precisam estar três vezes no Git se forem recuperáveis.
3. IPVA: `dados_complementares/ipva_sp_2026/18_IPVA_SP_CENARIOS_BASE_2026.csv` (~12 MiB), mais `dados_padronizados/18_IPVA_SP_VALORES_VENAIS_2026.csv` (~5,3 MiB).
4. GeoJSON antigo de `dados_geograficos/execucoes/` (~5,1 MiB). Guardar snapshots geográficos por versão em Storage/PostGIS.

**Política-alvo:** Git mantém **código, configurações pequenas, metadados e arquivos de referência leves**; Storage mantém RAW e artefatos grandes; PostgreSQL/PostGIS guarda dados estruturados servidos ao site. Não retirar arquivos até testar um clone que os obtém do Storage.

## Sequência segura (recomendada)

```powershell
# 1. Conferir status e preservar ponto de retorno
git status --short
git branch backup/antes-limpeza-dados-2026-11

# 2. Testar os scripts e comparar quantitativos ANTES de mudar pastas
python -m unittest discover -v -p "test_*.py"

# 3. Conferir se o segundo computador restaura dados do Storage;
#    comparar SHA-256 contra o manifesto da origem
python infra_check.py

# 4. Depois de validar o Storage e a restauração dos XLSX do INMETRO,
#    remover APENAS o rastreamento (manter cópias no disco):
# git rm --cached -- "INMETRO-dados-brutos/dados-inmetro.xlsx"
# git rm --cached -- "INMETRO-dados-organizados/dados-inmetro-organizado.xlsx"

# 5. Inspecionar cada alteração antes de commit
git diff --cached --stat
git status --short
```

Os comandos 4 ficam **comentados de propósito** porque ainda falta prova documental de restauração desses arquivos. Para grandes diretórios, a migração deve ser feita de forma separada, com atualização de `dados_mestres/atual.json` e/ou leitor capaz de recuperar a versão exata do Storage.

## Sobre `.gitignore`

O arquivo atual já ignora `.env`, RAW locais, `dados_cache/` e `dados_relatorios/`. Acrescentar `dados_mestres/execucoes/`, `dados_geograficos/execucoes/` e `dados_padronizados/` **somente depois** de implementar o fluxo Storage → workspace de execução. Arquivos rastreados continuam rastreados mesmo quando correspondem a padrões de ignore.

## Critério de término da organização

- `git status` limpo e commits separados para documentação e migração.
- Nenhum segredo ou cópia RAW volumosa no novo baseline do Git.
- Scripts existentes passam nos testes e conseguem localizar as entradas a partir da arquitetura declarada.
- Checksums/proveniência disponíveis para snapshots e histórico.
- Outro computador consegue reconstruir as tabelas selecionadas e carregar OD/GeoJSON.
- README e inventário não apontam para arquivos que foram retirados sem substituição.
