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
Object Storage -> arquivos RAW originais e históricos
PostgreSQL/PostGIS -> dados estruturados, históricos e geográficos
metadata.coletas -> proveniência consultável
```

O OneDrive foi tratado como origem de transição. Os RAW principais já foram migrados para o Storage, o pipeline já consegue usar o Storage como origem e novas referências temporais devem ser adicionadas sem apagar versões anteriores. A fase só deve ser considerada totalmente concluída quando outro computador/usuário conseguir acessar o mesmo Storage e banco, validar a conexão e reproduzir uma carga.

### Entregáveis desta fase

- [x] utilitário de conexão PostgreSQL/PostGIS;
- [x] utilitário de Object Storage compatível com S3;
- [x] migração RAW não destrutiva com SHA-256;
- [x] verificação conjunta de banco e Storage;
- [x] DDL inicial versionado;
- [x] documentação da arquitetura e configuração;
- [x] criar/configurar o projeto de nuvem sob controle da equipe;
- [x] executar a primeira carga piloto em Storage + PostgreSQL;
- [x] migrar as fontes RAW principais para o Storage;
- [x] permitir que o pipeline leia RAW diretamente do Storage;
- [x] aceitar RAW compactado quando necessário (ex.: ANEEL CSV/CSV.GZ/ZIP);
- [ ] validar acesso por um segundo computador/usuário.

## Fase 4 — Recorte geográfico e validação técnica

| Tarefa | Prioridade | Status | Issue |
|---|---|---|---|
| Definir unidade geográfica da análise no município de São Paulo | Alta | 🔜 | [#31](https://github.com/DanielBaptista01/PI06-Visualizacao_de_dados/issues/31) |
| Configurar nova chave OCM e rodar pipeline completo | Alta | 🔜 | [#3](https://github.com/DanielBaptista01/PI06-Visualizacao_de_dados/issues/3) |
| Validar matching Uber × INMETRO × FIPE × SENATRAN | Alta | 🔜 | [#4](https://github.com/DanielBaptista01/PI06-Visualizacao_de_dados/issues/4) |

### Escopo geográfico adotado

- **Unidade analítica canônica:** Zona OD 2023.
- **Escopo detalhado do produto:** município de São Paulo.
- **RMSP:** permanece como contexto e como cobertura para fontes que só existem nessa granularidade.
- Cada Zona OD do município deve ser associada, quando houver fonte adequada, a **distrito, subprefeitura e município**.
- Nomes como **Interlagos, Santo Amaro, Jurubatuba e Socorro** podem ser usados como rótulos amigáveis de navegação, desde que a associação espacial seja documentada e não transforme nomes informais em limites oficiais sem fonte adequada.

### Regra de granularidade

1. Dado por Zona OD -> usar diretamente.
2. Dado pontual com latitude/longitude -> fazer join espacial para Zona OD.
3. Dado municipal -> manter como valor municipal/contextual; não fabricar variação entre zonas.
4. Dado não geográfico por veículo -> aplicar ao veículo/cenário, não à região.
5. Dados gerais e específicos convivem no mesmo modelo: o geral entra como parâmetro comum e o específico regionaliza apenas o que realmente varia no território.

## Fase 5 — Cruzamentos e modelo mestre de veículos

| Tarefa | Prioridade | Status | Issue |
|---|---|---|---|
| Formalizar chaves/granularidades dos cruzamentos | Alta | 🔜 | — |
| Criar tabela mestre de veículos | Alta | ⬜ | [#5](https://github.com/DanielBaptista01/PI06-Visualizacao_de_dados/issues/5) |

A tabela mestre deverá consolidar, quando disponível: marca, modelo, versão, ano, propulsão, categoria Uber, eficiência INMETRO, preço FIPE, presença na frota SENATRAN e informações ABVE.

Os cruzamentos devem ser definidos como `pergunta -> variável -> fonte -> granularidade -> chave -> variável derivada`, evitando merges globais sem finalidade analítica.

### Entregáveis práticos

- definir chave canônica de veículo;
- medir cobertura do matching entre Uber, INMETRO, FIPE e SENATRAN;
- marcar matches fracos ou ambíguos para revisão;
- classificar propulsão: combustão, híbrido, híbrido plug-in e elétrico;
- gerar uma tabela mestre reproduzível para ser usada nos cálculos seguintes.

## Fase 6 — Modelo econômico

| Tarefa | Prioridade | Status | Issue |
|---|---|---|---|
| Implementar custos energéticos por veículo e região | Alta | ⬜ | [#6](https://github.com/DanielBaptista01/PI06-Visualizacao_de_dados/issues/6) |
| Definir metodologia de receita e ponto de equilíbrio | Alta | ⬜ | [#7](https://github.com/DanielBaptista01/PI06-Visualizacao_de_dados/issues/7) |
| Pesquisar fontes econômicas complementares | Média | ⬜ | [#8](https://github.com/DanielBaptista01/PI06-Visualizacao_de_dados/issues/8) |
| Implementar cenário de veículo alugado | Média | ⬜ | [#9](https://github.com/DanielBaptista01/PI06-Visualizacao_de_dados/issues/9) |

### Sequência de cálculo

1. custo de gasolina/etanol por km usando ANP + INMETRO;
2. custo elétrico por km usando ANEEL/recarga pública + INMETRO;
3. custo por turno/dia a partir de distância e tempo operacional;
4. receita bruta estimada por hora/km/corrida, com hipótese explicitada;
5. ponto de equilíbrio mínimo em R$/km e R$/hora;
6. adicionar manutenção, pneus, seguro, IPVA/licenciamento e depreciação;
7. comparar veículo próprio × alugado usando Uber Match;
8. produzir resultado econômico por cenário.

### Lacunas ainda abertas

- remuneração/receita do motorista por corrida, km ou hora;
- manutenção e pneus;
- seguro;
- IPVA/licenciamento;
- preço efetivo de recarga pública;
- trânsito/tempo de deslocamento, apenas se demonstrar relevância material.

Enquanto a receita não tiver fonte observável adequada, o projeto deve distinguir **custo operacional / ponto de equilíbrio** de **lucro observado**.

## Fase 7 — Tabela analítica final

O produto analítico antes da visualização deve convergir para uma granularidade semelhante a:

```text
Zona OD × faixa horária × veículo × categoria Uber × cenário
```

Campos esperados incluem:

- identificadores territoriais e rótulos amigáveis;
- demanda/viagens OD e tempo/distância;
- veículo e propulsão;
- eficiência e custo energético;
- receita estimada e ponto de equilíbrio;
- custos complementares;
- cenário próprio/alugado;
- indicadores de qualidade e origem das variáveis;
- resultado econômico estimado.

## Fase 8 — Automação

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

## Fase 9 — Backend e consumo dos dados

| Tarefa | Prioridade | Status | Issue |
|---|---|---|---|
| Criar backend/API para servir os dados ao site | Média | ⬜ | [#12](https://github.com/DanielBaptista01/PI06-Visualizacao_de_dados/issues/12) |

O frontend não deve depender diretamente de Excel/CSV em produção.

## Fase 10 — Visualização

| Tarefa | Prioridade | Status | Issue |
|---|---|---|---|
| Desenvolver narrativa e mapa interativo da RMSP / município de São Paulo | Alta | ⬜ | [#13](https://github.com/DanielBaptista01/PI06-Visualizacao_de_dados/issues/13) |

A proposta atual considera narrativa em scroll, mapa por Zona OD e comparação de cenários/veículos. O detalhamento principal será no município de São Paulo, com a RMSP preservada como contexto. A visualização vem depois da validação do modelo analítico.

## Fase 11 — Qualidade, documentação e entrega

| Tarefa | Prioridade | Status | Issue |
|---|---|---|---|
| Testes, documentação metodológica e publicação final | Alta | ⬜ | [#14](https://github.com/DanielBaptista01/PI06-Visualizacao_de_dados/issues/14) |

---

## Sequência operacional recomendada a partir de agora

1. **Congelar um baseline de dados**: registrar quais referências de ANP, ANEEL, SENATRAN, INMETRO, FIPE, ABVE, Uber e OD entram na primeira análise. Atualizações futuras entram como novas referências e permitem recalcular o baseline.
2. **Issue #31 — fechar o recorte geográfico**: filtrar Zonas OD do município de São Paulo, associar distrito/subprefeitura e definir rótulos amigáveis como Interlagos, Santo Amaro, Jurubatuba e Socorro.
3. **Issue #3 — validar pipeline completo** com Storage, banco e APIs configurados.
4. **Issue #4 — validar matching de veículos** e revisar ambiguidades.
5. **Formalizar o mapa de cruzamentos** `pergunta -> variável -> fonte -> granularidade -> chave -> derivação`.
6. **Issue #5 — criar a tabela mestre de veículos**.
7. **Issue #6 — calcular custo energético por km, hora e turno**.
8. **Issue #7 — definir receita e ponto de equilíbrio**; até lá, não chamar o resultado de lucro observado.
9. **Issue #8 — adicionar custos complementares**: manutenção, pneus, seguro, IPVA/licenciamento, depreciação e recarga pública.
10. **Issue #9 — comparar cenário próprio × alugado**.
11. **Consolidar a tabela analítica final** em `Zona OD × faixa horária × veículo × categoria Uber × cenário`.
12. **Issue #11 — automatizar atualizações** das fontes que mudam periodicamente.
13. **Issue #12 — criar API/backend**.
14. **Issue #13 — construir narrativa e mapa interativo**.
15. **Issue #14 — testes, metodologia, limitações e publicação final**.
16. **Issue #10 — fechar infraestrutura** assim que o segundo computador/usuário reproduzir acesso e carga compartilhada; essa validação pode ocorrer em paralelo às etapas analíticas.

## Como manter este roadmap

Sempre que uma tarefa avançar:

1. atualizar o status neste arquivo;
2. registrar decisões e evidências na Issue correspondente;
3. fechar a Issue quando os critérios de conclusão forem atendidos;
4. abrir nova Issue somente quando surgir uma tarefa realmente nova.

Assim o histórico do GitHub mostra tanto **o que foi feito** quanto **o que ainda falta**.
