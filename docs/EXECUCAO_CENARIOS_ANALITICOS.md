# PI06 — Cenários analíticos (bloco anterior ao backend)

**Referência:** desenvolvimento em 14/11/2026; compatível com `main` revisada até `ea161598`.

O bloco lê os **artefatos já gerados** pela OD 2023, consolidação INMETRO e motor econômico, e transforma os resultados em seis CSVs de consumo por painel. **Não modifica nenhum dado de entrada, não exige credenciais e não escreve no Supabase.**

## Arquivos do pacote e destino

| Novo arquivo | Copiar para |
|---|---|
| `gerar_cenarios_analiticos.py` | raiz do repositório (por compatibilidade com comandos atuais) |
| `testes/test_gerar_cenarios_analiticos.py` | pasta `testes/` já existente |
| `dados_config/cenarios_receita_analitica.csv` | `dados_config/` |
| `db/005_cenarios_analiticos.sql` | `db/` — **não executar em produção sem aplicar/carregar 001–004** |
| `docs/CENARIOS_ANALITICOS_IMPLEMENTADOS.md` | `docs/` |

Nenhum arquivo anterior será substituído. Este guia tem nome próprio para não sobrescrever o README.md principal do GitHub. O SQL `005` cria views e uma tabela de premissas vazia, mas não importa CSVs e não altera a operação do backend atual.

## Executar — PowerShell, na raiz do repositório

```powershell
python -m unittest discover -s testes -t . -p "test_*.py" -v
python gerar_cenarios_analiticos.py
```

Se um dos caminhos de saída já existir, a execução falhará intencionalmente. Para recalcular **somente os arquivos analíticos derivados**:

```powershell
python gerar_cenarios_analiticos.py --sobrescrever
```

Para usar os perfis econômicos da pesquisa opcional (em vez do arquivo `economia_completa` inicial):

```powershell
python gerar_cenarios_analiticos.py --economia dados_relatorios/economia_pesquisa_2026/resultado_motorista --saida dados_analiticos/cenarios_pesquisa_2026
```

**Se receber `Entrada ausente`**, rode antes os scripts que já estão no projeto:

```powershell
python consolidar_pi06.py
python economia_completa_pi06.py
python integrar_od2023.py --shape "ORIGEM_E_DESTINO_2023\002_SiteMetro Mapas_190225\Shape\Zonas_2023.shp" --sobrescrever
python gerar_cenarios_analiticos.py
```

> Não é necessário reprojetar os mapas novamente se os indicadores OD já existem; `gerar_cenarios_analiticos.py` apenas os lê.

## Saídas

Pasta padrão: `dados_analiticos/cenarios_2026/`.

| Arquivo | Granularidade e finalidade |
|---|---|
| `painel_od_zonas.csv` | **Zona OD**; amostra e viagens expandidas, presença de amostra e nomes para navegação |
| `painel_od_municipios.csv` | **Município OD**; totais e número de zonas com amostra |
| `painel_od_distritos_capital.csv` | **Distrito OD da capital**; totais e número de zonas com amostra |
| `painel_od_top_destinos.csv` | **Zona de origem × faixa × até cinco destinos**; fluxo e duração/distância em linha reta |
| `painel_energia_inmetro.csv` | **Versão INMETRO × modalidade**; custo energético/km e por km/mês hipotéticos |
| `painel_motorista_custos.csv` | **Perfil × versão INMETRO × modalidade**; custos identificados, campos pendentes e custos completos quando disponíveis |
| `dim_premissas_receita.csv` | **Hipótese de recebimento mensal após taxas da plataforma**, rotulada como didática |
| `painel_sensibilidade_receita.csv` | **Perfil × versão × modalidade × hipótese de receita**; só calcula resultado se o custo total for conhecido |
| `manifesto_cenarios_analiticos.json` | Contagens, datas, checksums SHA-256 e limitações |

No baseline informado pela equipe, são esperados **527 registros de zona**, **838 cenários energéticos** e **1.676 registros econômicos** (dois perfis). Com três hipóteses ilustrativas de receita, a sensibilidade terá **5.028 linhas**. A contagem real dependerá do arquivo econômico escolhido.

## Distinções obrigatórias

- `painel_od_*`: pesquisa Metrô 2023, `MODOPRIN=12`, **não exclusivamente Uber**; `FE_VIA` é expansão de viagens, não pessoas/veículos.
- `DISTANCIA` da OD é **linha reta**; não usar para custear uma corrida real.
- `painel_energia_inmetro.csv`: só tem versão INMETRO, **não associa** preço FIPE a essa versão.
- `subtotal_custos_conhecidos_rs_mes`: soma das parcelas existentes; **não é custo mensal total** quando há lacuna.
- `custo_total_economico_rs_mes`: vazio se faltar qualquer custo.
- `resultado_economico_simulado_rs_mes`: vazio se faltar custo total; receita é hipotética, não receita observada.
- Nenhum CSV contém `zona_od_id` junto a `inmetro_id`, porque não há dado que suporte lucro por zona.
- As linhas podem alimentar o backend como **painéis independentes**, não como um único fato universal.

## Próximo bloco de backend

1. Aplicar migrations em **banco de staging** e validar schema: `001` → `002` → `003` → `004` → `005`.
2. Carregar fatos OD, cenários INMETRO e motor econômico a partir dos CSVs originais; GeoJSON e checksums devem ser armazenados com a mesma versão.
3. Carregar a tabela `analytics.premissas_receita` com `dados_config/cenarios_receita_analitica.csv` (somente se o modo demonstrativo for habilitado).
4. Comparar `SELECT COUNT(*)` das views com os arquivos gerados e testar nulos, IDs e segurança.
5. Expor consultas de leitura com filtros, limite e paginação. Frontend não lê CSV diretamente em produção.

Não executar `db/005_cenarios_analiticos.sql` antes de existir a camada de base populada. As views dependem de nomes/colunas definidos em `db/002`, `003` e `004`.
