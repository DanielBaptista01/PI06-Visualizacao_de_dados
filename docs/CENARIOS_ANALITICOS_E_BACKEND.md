# Contrato analítico e proposta de backend — PI06

**Status:** desenho pronto para implementação; não significa que o PostGIS está populado ou que a API existe. Atualização 14/11/2026. Objetivo do bloco seguinte: montar as tabelas/views e testar antes do frontend.

## Decisão arquitetural essencial

**Não criar uma única tabela cartesiana `527 zonas × 4 faixas × 1.903 FIPE × categorias Uber × cenários econômicos`**. Isso explode a quantidade de linhas e inventa uma relação geográfica inexistente. Separar fatos territoriais (OD) de fatos econômicos (INMETRO/perfil/tarifa), e o frontend os mostra lado a lado sob filtros independentes. A geografia só altera um custo quando houver preço ou outra variável regional medida no nível correto.

## Granularidades e chaves propostas

| Produto / View | Granularidade mínima | Chave / origem | Métricas válidas |
| --- | --- | --- | --- |
| `geo.municipios_od2023` | Município OD | `municipio_od_id` | nome, qtd zonas, geometria se validada |
| `geo.zonas_od2023` | Zona OD 2023 | `zona_od_id` | município, distrito OD, escopo, polígono EPSG:4326 |
| `fato.od2023_origens_zona_faixa` | Zona × faixa horária | `zona_od_id, faixa_horaria` | amostra, expansão, duração e linha reta ponderadas |
| `fato.od2023_destinos_zona_faixa` | Zona × faixa horária | idem | viagens chegando, qualidade de amostra |
| `fato.od2023_fluxos_zona_faixa` | Zona origem × zona destino × faixa | `zona_origem_id, zona_destino_id, faixa_horaria` | fluxo, expansão e métricas amostrais |
| `analytics.od2023_indicadores_zona` | Zona | view de `db/004_od2023_territorio.sql` | presença de amostra, totais descritos |
| `core/analytics` FIPE parcial | FIPE versão × ano × referência | `brand_id, model_id, year_code, mes_referencia` | preço e status de cobertura |
| ponte FIPE × INMETRO | Candidato de relação | `veiculo_id, inmetro_id` | status `PENDENTE/APROVADO/REJEITADO`, evidência; nunca atribuir consumo se pendente |
| ponte FIPE × Uber | Versão FIPE × categoria/modelo Uber | identificação do vínculo/categoria | ano compatível, **não elegibilidade assegurada** |
| `analytics` energia INMETRO | `inmetro_id × modalidade × referência de cenário` | identificador do INMETRO e hipótese | custo energético/km; duração da tarifa, tributos e perdas |
| `analytics` motorista | perfil × `inmetro_id` × modalidade | `perfil_id, inmetro_id, modalidade` | custos/mês, equilíbrio/km/h, lucro **somente se completo** |
| OCM × zona | Ponto georreferenciado × zona (se join seguro) | `id_posto, zona_od_id` | quantidade de pontos catalogados, **não disponibilidade instantânea** |

**Importante:** códigos de município do Metrô (ex.: São Paulo = `36`) não são os códigos IBGE. Distritos da OD, distritos oficiais e subprefeituras do GeoSampa também requerem mapeamento explícito e revisão de limites.

## Cenários prioritários para o storytelling

### A. Onde estão os deslocamentos por aplicativo na OD 2023?

**Visual:** mapa de 39 municípios com drill-down na capital (343 zonas). Exibir número de **viagens expandidas**, contagem amostral, origens e destinos e faixa horária. Permitir destacar zonas sem amostra, que **não têm zero comprovado**. `MODOPRIN=12` inclui táxi não convencional/aplicativo.

### B. Como os fluxos variam por origem, destino e horário?

**Visual:** click na zona → destinos principais, amostra e duração/distância **em linha reta**. A distância não é percurso rodado pelo motorista; não usá-la diretamente para estimar custo por corrida real sem modelo específico de rede viária e km ocioso.

### C. Quanto custa a energia por tecnologia e versão INMETRO?

**Visual:** comparar versões e modalidades gasolina/etanol/híbrido/elétrico, preço ANP de novembro/2026, tarifa residencial ANEEL sem tributos e recarga pública como hipótese separada. Gráfico R$/km e R$ por 3.000 km **hipotéticos**. Não anexar um preço FIPE a versão INMETRO com match pendente.

### D. Qual o custo mensal e ponto de equilíbrio para um motorista?

**Visual:** regime `proprio` ou `alugado`, 3.000 km e 200h como defaults **editáveis e hipotéticos**; custos por componente; receita da plataforma editável pelo usuário. Quando faltarem dados, mostrar `PARCIAL_PENDENTE` e campos ausentes. Sensibilidade por km/horas/receita; quando premissas completas, mostrar **resultado econômico simulado**, não lucro observado.

### E. Recarga e distribuição de eletrificados

**Visual:** pontos OCM em zonas OD com data do snapshot; oferta ABVE como contexto em granularidade municipal/temporal. Não inferir quantas unidades estão operacionais nem equiparar novas vendas a frota total.

### F. Contexto territorial e comparação independente

Ao clicar em uma zona, o painel pode combinar **indicador de mobilidade OD daquela zona** e **simulação de custo para um veículo escolhido**. Não significa que o custo é específico daquela zona: mostrar explicitamente “mesma hipótese econômica aplicada ao perfil, não estimada pela OD”. Se houver preço ANP municipal comprovado, a mudança regional é por município; não interpolar automaticamente para zonas.

## Carga e API: ordem recomendada

1. Conferir `db/001_init.sql` e aplicar migrations `002`, `003`, `004` em banco de staging com backup e checagem de schema.
2. Copiar arquivos de `dados_relatorios/territorio_od2023/` e consolidação econômica para Storage ou pasta de carga reprodutível com SHA-256.
3. Carregar `geo.municipios_od2023`, `geo.zonas_od2023` e fatos OD; verificar contagens, FKs, chaves e geometria válida.
4. Carregar cenários INMETRO e perfis completos/parciais com indicadores de qualidade; não elevar vínculo FIPE pendente a aprovado.
5. Construir views materializadas ou consultas parametrizadas para mapa, faixa horária, fluxos e comparador.
6. Implementar API de leitura (servidor ou PostgREST/Supabase) com paginação, validação dos parâmetros, segurança e cache.
7. Integrar frontend apenas após testes de consistência entre CSV, SQL e respostas da API.

## Endpoints indicativos (não implementados)

```text
GET /api/od/municipios
GET /api/od/municipios/36/zonas
GET /api/od/municipios/36/distritos
GET /api/od/zonas/{zona_od_id}?faixa=Manhã
GET /api/od/zonas/{zona_od_id}/destinos?faixa=Manhã&limite=20
GET /api/energia/cenarios?tecnologia=Eletrico&km_mes=3000
GET /api/economia/cenarios?perfil=proprio_custo_referencial_2026
GET /api/economia/premissas
GET /api/recarga/pontos?municipio_od_id=36
```

A API deve aceitar apenas filtros previamente definidos, limitar resultados por chamada e devolver `fonte`, `periodo_referencia`, `natureza_dado` (`observado`, `derivado`, `simulado`, `pendente`), `granularidade` e `limitações`. O usuário poderá selecionar veículo e região sem que isso autorize calcular “lucro por região”.

## Qualidade mínima exigida para liberar o backend

- 527 zonas e 39 municípios; 343 zonas e 96 distritos no município São Paulo segundo catálogo OD.
- Dados de OD: 4.229 registros modo 12, soma de pesos 1.041.875,01 para a amostra atual; todas as zonas de origem e destino em referência.
- Os 13 artefatos da OD publicados devem apresentar checksum, data e código de versão.
- Em 2026, 838 simulações INMETRO e 1.676 combinações com perfis iniciais; dados sem receita completa permanecem `NULL` para lucro.
- Geometrias EPSG:4326 válidas; auditar alterações e verificar visualmente os contornos.
- Conservar status dos matches; 0 homologações automáticas no baseline.
- Reproduzir os testes unitários e de integração após qualquer reorganização de pastas.

## O que não está sendo prometido

Sem viagens reais da plataforma, preços georreferenciados confiáveis por zona, receita por corrida e relação homologada de veículo, **não há cálculo observacional de ganho de motorista por zona OD**. O produto pode, legitimamente, mostrar demanda OD 2023 e **simulador financeiro genérico do motorista** lado a lado.
