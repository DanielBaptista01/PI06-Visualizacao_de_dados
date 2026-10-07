# Roadmap do projeto

Este arquivo é a visão geral do PI. As tarefas executáveis ficam em **GitHub Issues** e devem ser fechadas conforme forem concluídas.

## Convenção de prioridade

- **Alta**: bloqueia ou influencia diretamente a infraestrutura, o modelo econômico ou a entrega.
- **Média**: importante, mas depende de etapas anteriores ou pode ser feita depois do núcleo.
- **Baixa**: melhoria opcional ou exploração futura.

## Status

- ✅ Concluído
- 🔄 Em andamento
- 🔜 Próximo
- ⬜ Pendente

---

## Fase 1 — Levantamento e fontes

| Tarefa | Prioridade | Status |
|---|---|---|
| Mapear fontes de dados do projeto | Alta | ✅ |
| Obter ANP, ANEEL, INMETRO, SENATRAN, ABVE, Uber e Open Charge Map | Alta | ✅ |
| Obter microdados OD 2023 (.sav/.dbf) | Alta | ✅ |
| Obter Shape das Zonas OD 2023 | Alta | ✅ |
| Obter malha municipal do IBGE | Alta | ✅ |
| Validar escopo territorial RMSP / 527 Zonas OD | Alta | ✅ |

## Fase 2 — Refatoração do pipeline

| Tarefa | Prioridade | Status |
|---|---|---|
| Revisar o `extrair.py` original | Alta | ✅ |
| Separar bases locais, APIs e FIPE | Alta | ✅ |
| Transformar `extrair.py` em orquestrador | Alta | ✅ |
| Corrigir processamento da OD para usar microdados | Alta | ✅ |
| Separar tabelas SENATRAN por granularidade | Alta | ✅ |
| Alterar ABVE de Município de São Paulo para RMSP | Alta | ✅ |
| Criar FIPE incremental com cache/checkpoint | Alta | ✅ |
| Remover chave OCM do código | Alta | ✅ |
| Criar manifesto de proveniência local | Alta | ✅ |
| Melhorar `explorar.py` para catálogo/qualidade | Média | ✅ |

## Fase 3 — Infraestrutura e organização definitiva dos dados

| Tarefa | Prioridade | Status | Issue |
|---|---|---|---|
| Modelar PostgreSQL + PostGIS, Storage e proveniência compartilhada | Alta | 🔄 | [#10](https://github.com/DanielBaptista01/PI06-Visualizacao_de_dados/issues/10) |

Arquitetura adotada:

```text
GitHub -> código, documentação e DDL
Object Storage -> arquivos RAW originais
PostgreSQL/PostGIS -> dados estruturados, históricos e geográficos
metadata.coletas -> proveniência consultável
```

O OneDrive atual é a origem de transição dos arquivos já coletados. A fase só deve ser considerada concluída quando outro computador conseguir acessar o mesmo Storage e banco, validar a conexão e reproduzir uma carga sem depender de arquivos enviados manualmente.

### Entregáveis desta fase

- [x] utilitário de conexão PostgreSQL/PostGIS;
- [x] utilitário de Object Storage compatível com S3;
- [x] migração RAW não destrutiva com SHA-256;
- [x] verificação conjunta de banco e Storage;
- [x] DDL inicial versionado;
- [x] documentação da arquitetura e configuração;
- [ ] criar/configurar o projeto de nuvem sob controle da equipe;
- [ ] executar a primeira carga piloto em Storage + PostgreSQL;
- [ ] validar acesso por um segundo computador/usuário;
- [ ] migrar gradualmente as fontes existentes.

## Fase 4 — Validação técnica da coleta

| Tarefa | Prioridade | Status | Issue |
|---|---|---|---|
| Configurar nova chave OCM e rodar pipeline completo | Alta | 🔜 | [#3](https://github.com/DanielBaptista01/PI06-Visualizacao_de_dados/issues/3) |
| Validar matching Uber × INMETRO × FIPE × SENATRAN | Alta | 🔜 | [#4](https://github.com/DanielBaptista01/PI06-Visualizacao_de_dados/issues/4) |

## Fase 5 — Cruzamentos e modelo mestre de veículos

| Tarefa | Prioridade | Status | Issue |
|---|---|---|---|
| Formalizar chaves/granularidades dos cruzamentos | Alta | 🔜 | — |
| Criar tabela mestre de veículos | Alta | ⬜ | [#5](https://github.com/DanielBaptista01/PI06-Visualizacao_de_dados/issues/5) |

A tabela mestre deverá consolidar, quando disponível: marca, modelo, versão, ano, propulsão, categoria Uber, eficiência INMETRO, preço FIPE, presença na frota SENATRAN e informações ABVE.

Os cruzamentos devem ser definidos como `pergunta -> variável -> fonte -> granularidade -> chave -> variável derivada`, evitando merges globais sem finalidade analítica.

## Fase 6 — Modelo econômico

| Tarefa | Prioridade | Status | Issue |
|---|---|---|---|
| Implementar custos energéticos por veículo e região | Alta | ⬜ | [#6](https://github.com/DanielBaptista01/PI06-Visualizacao_de_dados/issues/6) |
| Definir metodologia de receita e ponto de equilíbrio | Alta | ⬜ | [#7](https://github.com/DanielBaptista01/PI06-Visualizacao_de_dados/issues/7) |
| Pesquisar fontes econômicas complementares | Média | ⬜ | [#8](https://github.com/DanielBaptista01/PI06-Visualizacao_de_dados/issues/8) |
| Implementar cenário de veículo alugado | Média | ⬜ | [#9](https://github.com/DanielBaptista01/PI06-Visualizacao_de_dados/issues/9) |

### Lacunas ainda abertas

- remuneração/receita do motorista por corrida, km ou hora;
- manutenção e pneus;
- seguro;
- IPVA/licenciamento;
- preço efetivo de recarga pública;
- trânsito/tempo de deslocamento, apenas se demonstrar relevância material.

Enquanto a receita não tiver fonte observável adequada, o projeto deve distinguir **custo operacional / ponto de equilíbrio** de **lucro observado**.

## Fase 7 — Automação

| Tarefa | Prioridade | Status | Issue |
|---|---|---|---|
| Automatizar coletas conforme periodicidade real das fontes | Média | ⬜ | [#11](https://github.com/DanielBaptista01/PI06-Visualizacao_de_dados/issues/11) |

Periodicidades de referência:

- ANP: semanal;
- ANEEL tarifas: semanal;
- bandeira tarifária: mensal;
- SENATRAN: mensal;
- FIPE: mensal;
- ABVE: mensal;
- Open Charge Map: diária;
- Uber/INMETRO: checagem por alteração;
- IBGE: anual;
- OD 2023: estática com controle de versão.

## Fase 8 — Backend e consumo dos dados

| Tarefa | Prioridade | Status | Issue |
|---|---|---|---|
| Criar backend/API para servir os dados ao site | Média | ⬜ | [#12](https://github.com/DanielBaptista01/PI06-Visualizacao_de_dados/issues/12) |

O frontend não deve depender diretamente de Excel/CSV em produção.

## Fase 9 — Visualização

| Tarefa | Prioridade | Status | Issue |
|---|---|---|---|
| Desenvolver narrativa e mapa interativo da RMSP | Alta | ⬜ | [#13](https://github.com/DanielBaptista01/PI06-Visualizacao_de_dados/issues/13) |

A proposta atual considera narrativa em scroll, mapa por Zona OD e comparação de cenários/veículos. A visualização vem depois da validação do modelo analítico.

## Fase 10 — Qualidade, documentação e entrega

| Tarefa | Prioridade | Status | Issue |
|---|---|---|---|
| Testes, documentação metodológica e publicação final | Alta | ⬜ | [#14](https://github.com/DanielBaptista01/PI06-Visualizacao_de_dados/issues/14) |

---

## Ordem recomendada de execução

1. Issue #10 — concluir infraestrutura compartilhada e primeira carga piloto.
2. Issue #3 — validar pipeline completo com credenciais/configuração atualizadas.
3. Issue #4 — validar matching de veículos.
4. Formalizar o mapa de cruzamentos e granularidades.
5. Issue #5 — criar a tabela mestre de veículos.
6. Issues #6 e #7 — fechar custos e metodologia econômica.
7. Issues #8 e #9 — complementar fontes e cenário de aluguel.
8. Issue #11 — automatizar atualizações.
9. Issue #12 — criar a API/backend.
10. Issue #13 — construir a visualização final.
11. Issue #14 — testes, documentação e publicação.

## Como manter este roadmap

Sempre que uma tarefa avançar:

1. atualizar o status neste arquivo;
2. registrar decisões e evidências na Issue correspondente;
3. fechar a Issue quando os critérios de conclusão forem atendidos;
4. abrir nova Issue somente quando surgir uma tarefa realmente nova.

Assim o histórico do GitHub mostra tanto **o que foi feito** quanto **o que ainda falta**.
