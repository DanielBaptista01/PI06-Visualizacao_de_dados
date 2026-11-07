# Inventário inicial dos dados existentes

Este documento registra a estrutura de alto nível observada na pasta compartilhada `PI06-Visualizacao-de-dados-brutos` no OneDrive. Ele não substitui o catálogo técnico de arquivos; serve como referência para a migração para Object Storage e PostgreSQL/PostGIS.

## Pastas de fonte identificadas

- `ABVE/`
- `ANEEL/`
- `ANP/`
- `FIPE/`
- `IBGE—mapa_da_RMSP/`
- `INMETRO/`
- `ORIGEM_E_DESTINO_2023/`
- `SENATRAN/`
- `UBER/`
- `UBER_MATCH/`

## Pastas geradas pelo pipeline

- `dados_cache/`: cache reconstruível e checkpoints;
- `dados_limpos/`: saídas tratadas e snapshots de trabalho;
- `dados_relatorios/`: manifesto e relatórios locais.

## Arquivos de código/configuração observados na cópia

A cópia do OneDrive também contém alguns arquivos do projeto, como `.env.example`, `.gitignore`, `explorar.py`, `extrair.py` e `extrair_apis.py`. O GitHub deve permanecer como fonte oficial do código; esses arquivos no OneDrive não devem ser tratados como cópia canônica.

## Classificação para migração

| Tipo | Destino principal | Regra |
|---|---|---|
| arquivo original da fonte | Object Storage `raw/` | preservar bytes e SHA-256 |
| cache/checkpoint | local ou Storage apenas se necessário | reconstruível; não é fonte primária |
| CSV/GeoJSON tratado | PostgreSQL/PostGIS e/ou snapshot leve | preservar granularidade e referência temporal |
| relatório/manifesto | `metadata` no PostgreSQL + relatório local | proveniência consultável |
| código | GitHub | não duplicar como fonte oficial no Storage |

## Regra de transição

O inventário do OneDrive é uma fotografia da origem atual, não a arquitetura definitiva. Durante a migração:

1. o arquivo original continua no OneDrive até a cópia para Storage ser validada;
2. o upload RAW recebe SHA-256;
3. a proveniência é registrada no banco;
4. só depois a equipe passa a tratar o Storage como origem operacional daquela cópia;
5. não é necessário apagar a versão do OneDrive para concluir a migração.

## Próxima validação do inventário

Antes da migração completa, cada pasta de fonte deve receber uma ficha com:

- arquivos existentes;
- formato/extensão;
- tamanho;
- período de referência;
- granularidade;
- chave potencial;
- frequência de atualização;
- destino `raw/` recomendado;
- tabela PostgreSQL/PostGIS correspondente, quando definida.

A migração deve começar por uma fonte pequena, em modo `--dry-run`, e só depois avançar para bases maiores.


## Situação da base FIPE — novembro de 2026

**Status:** coleta parcial validada estruturalmente.

### Origem
- Fonte de consulta: API FIPE Parallelum v2.
- Referência dos preços: novembro de 2026.
- Arquivo tratado: `dados_limpos/08_FIPE_VEICULOS_PARCIAL.csv`.
- Histórico: `dados_cache/fipe_precos_catalogados_checkpoint.csv`.
- Catálogo: `dados_cache/fipe_catalogo.json`.

### Cobertura
- Versões candidatas coerentes identificadas: 4.969.
- Versões sem catálogo de anos: 56.
- Combinações versão/ano no recorte: 6.954.
- Combinações com preço: 489.
- Combinações sem preço: 6.465.
- Cobertura do recorte catalogado: 7,03%.

### Qualidade
- Duplicatas nas combinações coletadas: 0.
- Identificadores ausentes: 0.
- Campos obrigatórios ausentes: 0.
- Preços inválidos na validação monetária: 0.
- Referência mensal: novembro de 2026.

### Limitações
A coleta foi interrompida devido à limitação de acesso
à API. A base não representa o universo completo de
veículos ou versões FIPE.

A associação entre modelos Uber e FIPE é preliminar.
Os preços não comprovam elegibilidade para categorias
UberX, Comfort, Black ou Electric.

Os registros faltantes não são convertidos em zero.

### Situação da entrega
A base FIPE parcial está disponível para análises
exploratórias, desde que a cobertura limitada seja
informada e que não sejam feitas generalizações
estatísticas para todo o universo de veículos.
