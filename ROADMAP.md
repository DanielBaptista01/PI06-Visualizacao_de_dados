# ROADMAP — PI06 Visualização de Dados

**Última revisão documental:** 14/11/2026. Baseline do código consultado: commit `9337f69347718e04117fcf526e1b931db5e26a6f` (`exclusao-dados-de-teste`). Os status se referem às **entregas técnicas comprovadas**; scripts ou SQL publicados não equivalem à carga no banco ou a uma análise estatística finalizada.

Legenda: **✅ executado e validado no escopo definido** · **🟡 parcial / precisa integração** · **⬜ pendente**.

| Bloco | Status | Evidência / critério pendente |
| --- | --- | --- |
| Fontes principais e ETL Python | ✅ | ANP, ANEEL, SENATRAN, INMETRO, FIPE parcial, Uber, ABVE, IBGE, OD; refs congeladas no inventário |
| Storage + PostgreSQL básico | 🟡 | Objetos RAW e schemas iniciais configurados; ainda validar acesso e reprodução por outro computador |
| Padronização e tabelas-mestras por domínio | ✅ | `padronizar_bases.py` e `construir_tabelas_mestres.py` existentes; snapshots atuais exigem política de publicação |
| FIPE × INMETRO × Uber: candidatos | ✅ | `consolidar_pi06.py`; 1.903 FIPE, 1.284 com candidatos INMETRO; nenhuma versão homologada automaticamente |
| Homologação individual de versões e elegibilidade Uber | 🟡 | Dados mantidos como candidatos; selecionar evidências quando necessário para comparar um veículo específico |
| Motor econômico energético | ✅ | ANP, ANEEL e INMETRO; 838 cenários por versão INMETRO/modalidade |
| Cálculo econômico próprio/alugado | ✅ | Fórmula e testes implementados; saídas iniciais com 1.676 cenários pendentes por dados ausentes |
| Fontes econômicas complementares | 🟡 | Catálogo e valores de referência; receita observada comparável, seguro e IPVA individual ainda incompletos |
| OD 2023 estatística + geometrias | ✅ | 527 zonas, 39 municípios, 343 capital, 96 distritos; quatro testes sintéticos e processamento real registrados |
| Revisão visual das geometrias e cruzamento com GeoSampa | 🟡 | Reparos geométricos auditados; revisar mapa e versões de limites oficiais antes de publicar |
| Limpeza de backups e testes antigos no GitHub | ✅ | Commit `9337f69`; 45 arquivos a menos do que na versão anterior |
| Redução de CSVs pesados em Git | 🟡 | Ainda ~405 MiB de conteúdo; migrar outputs e validar reidratação pelo pipeline |
| Documentação técnica do estado atual | 🟡 | Pacote de atualização preparado; aplicar commit da documentação |
| Contrato analítico de mobilidade e cenários econômicos | 🟡 | Especificação proposta; ainda gerar views/cargas e testes integrados reais |
| PostgreSQL/PostGIS com tabelas populadas | ⬜ | Executar migrações, carregar dimensões/fatos e aferir contagens/consistência |
| Backend/API e políticas de acesso | ⬜ | Endpoints, filtros, cache, paginação, permissões e rastreabilidade |
| Site interativo e narrativa em scroll | ⬜ | Implementar UI, mapa, comparações e avisos de inferência |
| Revisão final/validação em segundo computador | ⬜ | Reproduzir pipeline e confirmar resultados/tempo de resposta |

## Próximo ciclo fechado: documentação → cenários → backend

### A. Organização e documentação (agora)

- [x] Identificar backups/testes duplicados e removê-los do versionamento.
- [ ] Aplicar o pacote de documentação atualizado, sem alterar scripts de produção neste commit.
- [ ] Auditar explicitamente o conteúdo de `dados_mestres/atual.json` antes de retirar as execuções vinculadas.
- [ ] Confirmar que os RAW e snapshots no Storage têm SHA-256 e são recuperáveis por outro computador.
- [ ] Definir o conjunto mínimo versionado e adicionar exclusões ao `.gitignore` somente quando os pipelines forem independentes dos arquivos removidos.

**Critério:** um clone limpo sabe onde encontrar cada dado e reproduz, ou recupera, as entradas da próxima etapa sem dependência acidental de versões locais.

### B. Tabelas e cenários analíticos

- [ ] Publicar visão `zona OD × faixa horária` com origens/destinos expandidos, amostra e indicador de dados ausentes.
- [ ] Publicar visão `zona origem × zona destino × faixa horária`, com distância **em linha reta** e duração ponderadas.
- [ ] Publicar visão de versões INMETRO × modalidade de combustível × cenário de tarifa; identificar versões sem preço FIPE homologado.
- [ ] Construir simulador próprio × alugado com **receita como entrada explícita** e análises de sensibilidade (km/mês e receita/horas), sem inventar lucro observado.
- [ ] Preparar topologia de pontos OCM com `latitude/longitude`, *spatial join* e distinção entre estação cadastrada e disponibilidade operacional.
- [ ] Manter OD 2023 e preços 2026 em dimensões temporais separadas; **nunca multiplicar as 1.041.875 viagens expandidas por lucro unitário hipotético para anunciar ganho total por zona**.
- [ ] Criar checagens de contagem, nulos, chaves, abrangência, referência temporal e proveniência para as views.

**Critério:** tabelas analíticas materializáveis, com dicionário de dados e consultas reproduzíveis sem junções indevidas.

### C. Backend/PostGIS

- [ ] Aplicar `db/001..004` de modo controlado após backup, comparar com banco existente e corrigir migrations se necessário.
- [ ] Carregar dimensões OD (527, 39, 96), fatos (1145 grupos origem, 1143 destino, 3383 fluxos) e geometria GeoJSON com contagem e integridade.
- [ ] Carregar dimensões e fatos econômicos sem declarar match FIPE–INMETRO como homologado.
- [ ] Definir API de municípios, distritos, zonas, fluxos, comparador e premissas com filtros e limites.
- [ ] Integrar autenticação/Row Level Security quando necessário; nenhum segredo no frontend.
- [ ] Verificar se métricas de zona são fonte OD ou cenários comuns apresentados na interface.

**Critério:** endpoints documentados retornam os mesmos totais que os CSVs/SQLs validados, e as geometrias carregam corretamente no mapa.

### D. Site e validação

- [ ] Narrativa sobre custos, eletrificação e mobilidade; depois mapa hierárquico e comparador de versões.
- [ ] Exibir legenda “MODO 12: táxi não convencional/aplicativo”; distinguir viagens expandidas da contagem amostral.
- [ ] Mostrar avisos de hipótese para médias de custo e receita; evitar mostrar preço FIPE de uma versão associado a consumo de outra.
- [ ] Testar performance de GeoJSON, simplificação cartográfica para web e responsividade.
- [ ] Conferir no mapa os contornos reparados e eventuais diferenças entre zoneamentos administrativos.

## Regras de gestão

- Um bloco só está ✅ quando artefato e validação existem. **Snapshot econômico parcial ≠ lucro final.**
- Testes unitários permanentes são parte do código; backups e exports brutos não precisam ser versionados.
- O histórico FIPE deve continuar incremental; status parcial representa o estágio da coleta, não uma falha.
- Preferir um commit de documentação, um de migração de dados e um de backend, para facilitar revisão e reversão.
- GitHub Issues permanecem como backlog granular; este arquivo acompanha o marco arquitetural e os bloqueios.
