# Pipeline usando RAW do Object Storage

## Objetivo

Permitir que o pipeline processe os arquivos RAW diretamente do Object Storage compartilhado, sem depender das pastas permanentes de um computador específico.

O Storage continua sendo a origem persistente. Durante a execução, somente os arquivos necessários são baixados para uma pasta temporária, processados e removidos automaticamente ao final.

## Regra para novas versões

Não apagar nem substituir silenciosamente versões antigas do RAW. Cada atualização deve receber uma nova referência temporal.

Exemplo para ANP:

```text
raw/anp/2026/08/arquivo.xlsx
raw/anp/2026/09/arquivo.xlsx
raw/anp/2026/10/arquivo.xlsx
```

Para fontes mensais, prefira `raw/<fonte>/<ano>/<mes>/...`. Para fontes anuais ou estáticas, o ano pode ser suficiente.

O pipeline seleciona automaticamente a referência numérica mais recente disponível para cada fonte antes de processar.

## Execução

Processar as bases baixando o RAW do Storage:

```powershell
python extrair.py bases --origem storage
```

Processar Uber Match usando os snapshots do Storage:

```powershell
python extrair.py uber-match --origem storage
```

Executar a sequência completa usando Storage para os grupos que dependem de RAW:

```powershell
python extrair.py tudo --origem storage
```

Os CSVs tratados continuam sendo gerados em `dados_limpos/`. O Storage é usado como origem dos arquivos brutos; esta mudança ainda não transforma os CSVs tratados em tabelas de domínio do PostgreSQL.

## Como funciona

1. o código lista os objetos de cada fonte no bucket;
2. identifica a referência temporal numérica mais recente;
3. baixa os objetos selecionados para uma pasta temporária;
4. aponta o pipeline para essa pasta durante a execução;
5. gera normalmente os arquivos em `dados_limpos/`;
6. remove a cópia temporária ao terminar.

Quando a origem de uma coleta é um arquivo baixado do Storage, o manifesto local tenta registrar o caminho `s3://...` em vez do caminho temporário.

## Fontes mapeadas

O modo Storage reconhece atualmente:

- ANEEL: `raw/aneel/`;
- ANP: `raw/anp/`;
- IBGE: `raw/ibge/`;
- INMETRO: `raw/inmetro/`;
- OD 2023: `raw/od2023/`;
- SENATRAN: `raw/senatran/`;
- ABVE manual: `raw/abve/manual/`;
- Uber: `raw/uber/`;
- Uber Match: `raw/uber_match/`.

## ANEEL e arquivos compactados

O CSV oficial de tarifas da ANEEL pode ultrapassar o limite de tamanho de arquivo do plano Free do Storage. Nesse caso, o RAW pode ser armazenado compactado, sem filtrar ou alterar as linhas da fonte.

O processador da ANEEL aceita atualmente:

- `.xlsx`;
- `.csv`;
- `.csv.gz`;
- `.zip` contendo um único CSV.

Exemplo recomendado para uma atualização publicada em 8 de outubro de 2026:

```text
raw/aneel/2026/10/08/tarifas-homologadas-distribuidoras-energia-eletrica.csv.gz
```

ou, se a compactação tiver sido feita pelo recurso ZIP do Windows:

```text
raw/aneel/2026/10/08/tarifas-homologadas-distribuidoras-energia-eletrica.zip
```

O pipeline lê o conteúdo compactado diretamente; não é necessário converter o arquivo para Excel nem filtrar o RAW antes do upload.

A base oficial de tarifas homologadas não expõe uma coluna de UF no esquema atual. Por isso, o processamento preserva os registros quando não houver campo de UF e registra essa condição na proveniência. O recorte correto para as distribuidoras que atendem a RMSP deve ser tratado em etapa analítica específica.

## Atualização dos arquivos RAW

O método recomendado continua sendo `migrar_raw.py`, porque ele calcula SHA-256 e registra a proveniência em `metadata.coletas`.

Exemplo:

```powershell
python migrar_raw.py --origem ".\ANP\Outubro-26" --fonte anp --prefixo raw/anp/2026/10 --referencia 2026-10 --dry-run
python migrar_raw.py --origem ".\ANP\Outubro-26" --fonte anp --prefixo raw/anp/2026/10 --referencia 2026-10
```

Também é possível enviar um arquivo manualmente pelo painel do Supabase para a nova pasta de referência. Nesse caso, o pipeline conseguirá lê-lo, mas `metadata.coletas` não será preenchida automaticamente por esse upload manual.

## O que não fazer

- não apagar agosto para colocar setembro;
- não substituir um arquivo antigo com conteúdo novo na mesma chave;
- não tratar `dados_limpos/` como RAW;
- não colocar credenciais no GitHub;
- não depender de uma pasta permanente no computador para executar `--origem storage`.

## Próxima evolução

Depois desta etapa, o próximo passo de arquitetura é carregar os dados CLEAN/FATO em PostgreSQL/PostGIS e permitir exportações CSV a partir do banco. Até isso ser implementado, os CSVs tratados continuam sendo saídas locais reproduzíveis do pipeline.
