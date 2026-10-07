# Arquitetura de dados do PI06

## Objetivo

Organizar os dados do projeto de forma reproduzível, compartilhável e independente de um computador específico. O GitHub continua sendo a fonte do código e da documentação; arquivos brutos ficam em Object Storage; dados estruturados e consultáveis ficam em PostgreSQL/PostGIS.

## Arquitetura-alvo

```text
Fontes externas / arquivos existentes
            |
            v
      Object Storage
      camada RAW imutável
            |
            v
      Pipeline Python
            |
     +------+------+
     |             |
     v             v
PostgreSQL     metadata.coletas
/PostGIS       proveniência
     |
     v
analytics / API / visualização
```

## Papel de cada tecnologia

### GitHub

Armazena código, DDL, documentação, configuração de exemplo e histórico de mudanças. Não deve receber credenciais reais nem bases brutas pesadas.

### OneDrive

É a origem de transição dos arquivos que já foram coletados pela equipe. A pasta atual `PI06-Visualizacao-de-dados-brutos` serve como ponto de inventário e primeira migração. Depois da migração e validação, o OneDrive deixa de ser a fonte operacional do pipeline.

### Object Storage

Armazena os arquivos RAW exatamente como vieram das fontes: CSV, XLSX, SAV, SHP, HTML, PDF e similares. O código usa protocolo S3, o que permite trabalhar com Supabase Storage ou outro provedor compatível.

Padrão recomendado de chave:

```text
raw/<fonte>/<ano>/<mes>/<arquivo-original>
```

Exemplos:

```text
raw/anp/2026/08/precos.xlsx
raw/senatran/2026/07/frota.xlsx
raw/od2023/2023/Banco2023_divulgacao_190225.sav
raw/uber_match/2026/10/locacoes.html
```

Arquivos RAW não devem ser sobrescritos silenciosamente. `migrar_raw.py` calcula SHA-256 e interrompe se encontrar, na mesma chave, conteúdo diferente, salvo quando a sobrescrita for solicitada explicitamente após revisão.

### PostgreSQL + PostGIS

Armazena os dados tratados e as relações entre fontes. PostGIS é usado para geometrias e consultas espaciais.

Schemas iniciais:

- `metadata`: fontes, execuções de coleta e proveniência;
- `core`: dimensões canônicas, como veículo e município;
- `geo`: geometrias e unidades espaciais, como Zonas OD;
- `fato`: observações históricas de cada fonte;
- `analytics`: variáveis derivadas e tabelas analíticas.

A migration `db/001_init.sql` cria os schemas, habilita PostGIS e cria `metadata.fontes` e `metadata.coletas`. As tabelas de domínio serão adicionadas em migrations posteriores, conforme as chaves analíticas forem fechadas.

## Camadas lógicas

### RAW

Arquivo original, preservado sem transformação. É a evidência da fonte.

### CLEAN / FATO

Dados padronizados, tipados e carregados no banco. Devem preservar a granularidade original da fonte.

### ANALYTICS

Variáveis criadas pelo projeto a partir de cruzamentos, por exemplo custo energético por km ou indicadores por Zona OD.

Não se deve apresentar uma variável de `analytics` como se tivesse sido fornecida diretamente pela fonte original.

## Proveniência

Cada arquivo efetivamente enviado ao Storage pode gerar um registro em `metadata.coletas`, contendo:

- fonte;
- data da coleta;
- data ou referência temporal do dado;
- origem relativa do arquivo;
- caminho no Storage;
- SHA-256;
- tamanho do arquivo;
- quantidade de registros quando conhecida;
- status;
- observações e metadados extras.

Uma nova execução que encontre o mesmo objeto com o mesmo SHA-256 faz `SKIP` e não cria uma coleta duplicada. O manifesto CSV atual continua útil durante a transição, mas o destino definitivo da proveniência é `metadata.coletas`.

## Configuração local

Copie `.env.example` para `.env` e preencha somente no computador local:

```powershell
Copy-Item .env.example .env
```

As principais variáveis são:

- `DATABASE_URL`;
- `S3_ENDPOINT_URL`;
- `S3_REGION`;
- `S3_ACCESS_KEY_ID`;
- `S3_SECRET_ACCESS_KEY`;
- `S3_BUCKET`;
- `OPEN_CHARGE_MAP_API_KEY`.

O arquivo `.env` nunca deve ser enviado ao GitHub.

## Inicialização e testes

Instale as dependências:

```powershell
python -m pip install -r requirements.txt
```

Aplique o DDL inicial:

```powershell
python database_utils.py init
```

Teste banco e Storage juntos:

```powershell
python infra_check.py
```

O diagnóstico só retorna sucesso quando PostgreSQL, PostGIS e Storage estão acessíveis.

Liste objetos no bucket:

```powershell
python storage_utils.py listar --prefixo raw/
```

A listagem usa paginação e não fica limitada aos primeiros mil objetos.

## Migração RAW

Antes de migrar, execute sempre um teste sem escrita:

```powershell
python migrar_raw.py --origem "C:\caminho\ANP" --fonte anp --prefixo raw/anp/2026/08 --referencia 2026-08 --dry-run
```

Depois de revisar os destinos:

```powershell
python migrar_raw.py --origem "C:\caminho\ANP" --fonte anp --prefixo raw/anp/2026/08 --referencia 2026-08
```

A migração não apaga a origem local. Por padrão, um objeto existente com conteúdo diferente interrompe a execução; `--sobrescrever` só deve ser usado após revisão explícita.

## Compartilhamento com a equipe

O acesso aos arquivos e ao banco deve ser concedido pelo próprio provedor de nuvem, por usuário/e-mail e com o menor nível de permissão necessário. Não se deve compartilhar senha de banco, access key ou arquivo `.env` pelo GitHub.

Um novo integrante deve conseguir:

1. receber acesso ao projeto de nuvem;
2. clonar o repositório;
3. criar sua própria `.env`;
4. instalar `requirements.txt`;
5. executar `python infra_check.py`;
6. consultar os mesmos dados da equipe.

## Critério de conclusão da fase de infraestrutura

A infraestrutura é considerada pronta quando um segundo computador consegue acessar o mesmo Storage e PostgreSQL/PostGIS, consultar a proveniência e reproduzir uma carga sem receber manualmente arquivos brutos da máquina original.
