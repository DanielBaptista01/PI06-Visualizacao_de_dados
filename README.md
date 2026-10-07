# PI06 — Visualização de dados

Projeto integrador de visualização de dados voltado à análise econômica de veículos a combustão, híbridos e elétricos no contexto de motoristas de aplicativo na Região Metropolitana de São Paulo (RMSP).

## Roadmap e acompanhamento

O andamento do projeto é acompanhado em [ROADMAP.md](ROADMAP.md). As tarefas pendentes possuem GitHub Issues com prioridade, dependências e critérios de conclusão.

A arquitetura de armazenamento e banco está documentada em [docs/ARQUITETURA_DADOS.md](docs/ARQUITETURA_DADOS.md).

## Organização do pipeline

- `extrair_bases.py`: processa bases baixadas (ANEEL, ANP, IBGE, INMETRO, SENATRAN, OD 2023, ABVE e regras Uber arquivadas).
- `extrair_apis.py`: coleta APIs externas. Atualmente contém Open Charge Map.
- `extrair_fipe.py`: pipeline FIPE incremental com mapeamento persistente, cache e checkpoint.
- `extrair_uber_match.py`: lê snapshots HTML do Uber Match, descobre as ofertas e coleta os detalhes de locação/compra.
- `extrair.py`: orquestrador.
- `explorar.py`: gera catálogo e relatório de qualidade/estrutura das fontes.
- `pipeline_utils.py`: funções compartilhadas de normalização, localização de arquivos e proveniência local.
- `database_utils.py`: conexão PostgreSQL/PostGIS, inicialização do DDL e proveniência no banco.
- `storage_utils.py`: acesso ao Object Storage compatível com S3.
- `migrar_raw.py`: migração não destrutiva de arquivos RAW para o Storage.
- `infra_check.py`: teste conjunto de banco e Storage.
- `db/001_init.sql`: DDL inicial versionado.

## Preparação do ambiente Python

Em um computador novo, as bibliotecas do projeto precisam ser instaladas **uma vez por ambiente**.

No Windows PowerShell:

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Em um novo terminal, basta reativar o ambiente:

```powershell
.\.venv\Scripts\Activate.ps1
```

Para conferir rapidamente:

```powershell
python -c "import pandas; import requests; import psycopg; import boto3; from bs4 import BeautifulSoup; print('Ambiente OK')"
```

A pasta `.venv/` é local e não deve ser enviada ao GitHub.

## Configuração local e segredos

Copie o arquivo de exemplo:

```powershell
Copy-Item .env.example .env
```

Preencha no `.env` local as credenciais necessárias, incluindo `DATABASE_URL`, as variáveis `S3_*` e a chave da Open Charge Map. O `.env` real está ignorado pelo Git e **nunca deve ser versionado**.

Como uma chave da Open Charge Map já esteve no histórico do repositório, a chave antiga deve permanecer revogada/rotacionada.

## Infraestrutura de dados

A arquitetura adotada separa responsabilidades:

```text
GitHub            -> código, documentação e DDL
Object Storage    -> arquivos RAW originais e imutáveis
PostgreSQL        -> dados estruturados e históricos
PostGIS           -> geometrias e consultas espaciais
metadata.coletas  -> proveniência das cargas
```

O OneDrive atual é tratado como **origem de transição** dos arquivos já coletados. Depois da migração e validação, o pipeline deve usar Storage e PostgreSQL/PostGIS como infraestrutura compartilhada, sem depender de uma pasta específica de um computador.

### Inicializar banco

Depois de configurar `DATABASE_URL`:

```powershell
python database_utils.py init
```

O comando aplica `db/001_init.sql`, habilita PostGIS e cria os schemas iniciais:

```text
metadata
core
geo
fato
analytics
```

### Testar banco e Storage

```powershell
python infra_check.py
```

### Migrar um conjunto RAW

Faça primeiro um dry-run:

```powershell
python migrar_raw.py --origem "C:\caminho\ANP" --fonte anp --prefixo raw/anp/2026/08 --referencia 2026-08 --dry-run
```

Depois de revisar:

```powershell
python migrar_raw.py --origem "C:\caminho\ANP" --fonte anp --prefixo raw/anp/2026/08 --referencia 2026-08
```

A origem não é apagada. O upload calcula SHA-256 e evita sobrescrever silenciosamente um objeto diferente.

## Execução do pipeline de coleta/limpeza

```powershell
python extrair.py bases
python extrair.py uber-match
python extrair.py apis
python extrair.py fipe
python explorar.py
```

Para executar tudo em sequência:

```powershell
python extrair.py tudo
```

## Uber Match — locação e compra

Os HTMLs gerais do Uber Match devem ser mantidos fora do GitHub como evidência da fonte, por exemplo:

```text
UBER_MATCH/
└── 2026-09/
    ├── uber_match_sao_paulo_locacoes.html
    └── uber_match_sao_paulo_compra.html
```

O diretório `UBER_MATCH/` está no `.gitignore`. O coletor encontra os links das ofertas, preserva páginas de detalhe, extrai os campos relevantes e gera:

```text
dados_limpos/17_UBER_MATCH_OFERTAS_SP.csv
dados_limpos/17_UBER_MATCH_FALHAS_SP.csv  # quando houver aviso/falha
```

Execução:

```powershell
python extrair.py uber-match
```

Para apenas validar os HTMLs e listar links sem acessar cada oferta:

```powershell
python extrair_uber_match.py --somente-indexar
```

Para baixar novamente páginas já preservadas localmente:

```powershell
python extrair_uber_match.py --atualizar
```

A tabela de ofertas inclui validações como `revisar_oferta`, `status_qualidade`, `motivos_revisao`, `apto_modelo_economico`, `valor_card_reais` e divergência entre preço do card e página individual. Registros problemáticos são preservados e marcados para revisão, não excluídos silenciosamente.

## Pesquisa OD 2023

O pipeline procura `Banco2023_divulgacao_190225.sav` ou `.dbf`, filtra `MODOPRIN = 12` e gera:

- `dados_limpos/07_OD2023_APP_MICRODADOS.csv`;
- `dados_limpos/07_OD2023_APP_ZONA_HORA.csv`;
- `dados_limpos/07_OD2023_ZONAS.geojson`, quando `Zonas_2023.shp` estiver disponível.

A distância da OD é tratada explicitamente como **distância em linha reta**. Médias agregadas de duração e distância são ponderadas por `FE_VIA`. O Shape é reprojetado para EPSG:4326 para uso em mapas web e joins por latitude/longitude.

## IBGE e RMSP

Quando o Shape municipal estiver presente, o pipeline recorta os municípios da RMSP a partir dos municípios existentes nas Zonas OD e gera GeoJSON em EPSG:4326. O Excel/DBF isolado continua servindo como fallback de atributos.

## SENATRAN

Os arquivos não são concatenados como se possuíssem o mesmo esquema. São separados por assunto/granularidade: combustível, marca/modelo, ano, potência, CEP e tipo de veículo.

## FIPE

A primeira execução cria um mapeamento persistente Uber → FIPE em `dados_cache/fipe_mapeamento.csv`. Nas próximas execuções o matching é reutilizado e só os preços precisam ser atualizados.

Há cache do catálogo, checkpoint, retomada, backoff para HTTP 429, marcação de matches fracos e filtro preliminar por modelos presentes no INMETRO quando isso é seguro.

Para refazer o matching:

```powershell
python extrair_fipe.py --remapear
```

Para revisar apenas o mapeamento:

```powershell
python extrair_fipe.py --somente-mapear
```

## Proveniência e reprodutibilidade

Durante a transição, o pipeline continua registrando eventos em `dados_relatorios/manifesto_coletas.csv`. A infraestrutura nova acrescenta `metadata.fontes` e `metadata.coletas` no PostgreSQL para tornar a proveniência consultável e compartilhada.

Entre os metadados preservados estão fonte, data/hora da coleta, data de referência, origem, caminho no Storage, quantidade de registros, SHA-256, status e metadados extras.

Os dados brutos pesados permanecem fora do Git. O repositório guarda código, documentação, DDL, arquivos processados leves quando fizer sentido e metadados de proveniência.

## Validação já realizada nesta refatoração

A lógica de OD foi testada com os microdados enviados no projeto: foram identificados **4.229 registros amostrais** com `MODOPRIN = 12`, correspondendo a aproximadamente **1.041.875 viagens expandidas** pelo fator `FE_VIA`.

Também foi validada a leitura das **527 Zonas OD 2023** e da malha municipal do IBGE; o recorte pelos municípios presentes nas Zonas OD resulta em **39 municípios da RMSP**.
