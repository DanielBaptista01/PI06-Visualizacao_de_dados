# PI06 — Visualização de dados

Projeto integrador de visualização de dados voltado à análise econômica de veículos a combustão, híbridos e elétricos no contexto de motoristas de aplicativo na Região Metropolitana de São Paulo (RMSP).

## Organização do pipeline

- `extrair_bases.py`: processa bases baixadas (ANEEL, ANP, IBGE, INMETRO, SENATRAN, OD 2023, ABVE e regras Uber arquivadas).
- `extrair_apis.py`: coleta APIs externas. Atualmente contém Open Charge Map.
- `extrair_fipe.py`: pipeline FIPE incremental com mapeamento persistente, cache e checkpoint.
- `extrair.py`: orquestrador.
- `explorar.py`: gera catálogo e relatório de qualidade/estrutura das fontes.
- `pipeline_utils.py`: funções compartilhadas de normalização, localização de arquivos e proveniência.

## Execução

```bash
pip install -r requirements.txt
python extrair.py bases
python extrair.py apis
python extrair.py fipe
python explorar.py
```

Para executar tudo em sequência:

```bash
python extrair.py tudo
```

## Segurança de APIs

A chave da Open Charge Map não fica mais no código. Defina:

```bash
export OPEN_CHARGE_MAP_API_KEY="..."
```

Use `.env.example` apenas como modelo. Como uma chave já esteve versionada no histórico do repositório, ela deve ser revogada/rotacionada no provedor.

## Pesquisa OD 2023

O pipeline deixa de concatenar planilhas heterogêneas. Ele procura `Banco2023_divulgacao_190225.sav` ou `.dbf`, filtra `MODOPRIN = 12` (táxi não convencional/aplicativo) e gera:

- `dados_limpos/07_OD2023_APP_MICRODADOS.csv`
- `dados_limpos/07_OD2023_APP_ZONA_HORA.csv`
- `dados_limpos/07_OD2023_ZONAS.geojson`, quando `Zonas_2023.shp` estiver disponível.

A distância da OD é tratada explicitamente como **distância em linha reta**, evitando confundi-la com distância real percorrida. Médias agregadas de duração e distância são ponderadas por `FE_VIA`.

O Shape é reprojetado para EPSG:4326 para uso em mapas web e joins por latitude/longitude.

## IBGE e RMSP

Quando o Shape municipal estiver presente, o pipeline recorta os municípios da RMSP a partir dos municípios existentes nas Zonas OD e gera GeoJSON em EPSG:4326. O Excel/DBF isolado continua servindo como fallback de atributos.

## SENATRAN

Os arquivos não são mais concatenados como se possuíssem o mesmo esquema. São separados por assunto/granularidade: combustível, marca/modelo, ano, potência, CEP e tipo de veículo.

## FIPE

A primeira execução cria um mapeamento persistente Uber → FIPE em `dados_cache/fipe_mapeamento.csv`. Nas próximas execuções o matching é reutilizado e só os preços precisam ser atualizados.

Há:
- cache do catálogo;
- checkpoint após cada consulta;
- retomada depois de interrupção;
- backoff para HTTP 429;
- marcação de matches fracos para revisão;
- filtro preliminar por modelos presentes no INMETRO quando isso é seguro.

Para refazer o matching:

```bash
python extrair_fipe.py --remapear
```

Para revisar apenas o mapeamento:

```bash
python extrair_fipe.py --somente-mapear
```

## Proveniência e reprodutibilidade

Cada processamento registra um evento em `dados_relatorios/manifesto_coletas.csv`, com:
- fonte;
- data/hora da coleta;
- data de referência;
- arquivo/URL de origem;
- arquivo de destino;
- quantidade de registros;
- SHA-256 do arquivo bruto, quando aplicável;
- observações e metadados extras.

Isso permite documentar **de onde o dado veio, quando foi coletado e qual arquivo gerou o derivado**.

Os dados brutos pesados permanecem fora do Git. O repositório deve guardar:
1. código;
2. documentação de fonte;
3. arquivos processados leves quando fizer sentido;
4. metadados de proveniência.

## Próxima etapa: armazenamento

A recomendação para o site é carregar os dados processados em **PostgreSQL + PostGIS**. Os arquivos fixos (OD, IBGE, INMETRO etc.) podem entrar como tabelas versionadas; dados recorrentes (ANP, ANEEL, FIPE, OCM etc.) devem preservar `data_referencia` e `data_coleta`.

O site/API então consulta o banco, enquanto o GitHub continua sendo a fonte do código e da documentação da coleta — não o banco operacional.

Uma estrutura futura pode separar:
- `fontes`: catálogo das fontes e URLs;
- `execucoes_coleta`: histórico, hash, versão e timestamps;
- tabelas dimensionais de veículos e regiões;
- tabelas históricas de preços/tarifas;
- tabelas geográficas PostGIS para municípios, Zonas OD e eletropostos.

## Validação já realizada nesta refatoração

A lógica de OD foi testada com os microdados enviados no projeto: foram identificados **4.229 registros amostrais** com `MODOPRIN = 12`, correspondendo a aproximadamente **1.041.875 viagens expandidas** pelo fator `FE_VIA`.

Também foi validada a leitura das **527 Zonas OD 2023** e da malha municipal do IBGE; o recorte pelos municípios presentes nas Zonas OD resulta em **39 municípios da RMSP**.
