# PI06 — Bloco OD 2023: integração territorial completa (v1)

Este pacote tem **dimensões já calculadas da planilha oficial da OD 2023** e um pipeline de viagens com opção de gerar GeoJSON a partir do **shape oficial**. Não substitui `extrair_bases.py`, `consolidar_pi06.py`, `economia_completa_pi06.py` ou as configurações econômicas; não se conecta ao Supabase nem altera RAW.

## Instalação em uma única vez

1. Extraia o conteúdo do ZIP na **raiz do repositório**, preservando `dados_referencia_od/`, `db/` e `docs/`. Nenhum arquivo do repositório com o nome `README.md` é substituído por este pacote.
2. Confirme que `dados_limpos/07_ORIGEM_DESTINO.csv` existe. Ele é gerado pelo `extrair_bases.py` a partir dos microdados OD do Metrô. Se o arquivo não estiver disponível, use `--entrada` com o caminho do `.sav` ou `.dbf` oficial.
3. Com `.venv` ativo, execute:

```powershell
python -m unittest -v test_integrar_od2023.py
python integrar_od2023.py
```

Serão criados os indicadores em `dados_relatorios/territorio_od2023/`. Se repetir a carga, use `--sobrescrever` para atualizar **somente as saídas derivadas**.

## Polígonos para mapa interativo (quando houver shape oficial)

O **Metrô** já publica `Zonas_2023.shp` e os arquivos associados `.dbf`, `.shx`, `.prj` e `.cpg` no pacote de anexos OD 2023. Não precisa desenhar as 527 zonas no GeoSampa; preserve esses arquivos **juntos na mesma pasta**. Se o SHP já foi migrado para o Storage, baixe os arquivos correspondentes pelo fluxo de Storage da equipe.

Localize o arquivo no Windows:

```powershell
Get-ChildItem -Path . -Recurse -Filter Zonas_2023.shp | Select-Object -ExpandProperty FullName
```

Após descobrir o caminho real, rode (substitua o exemplo):

```powershell
python integrar_od2023.py --shape "C:\caminho\dos\shapes\Zonas_2023.shp" --sobrescrever
```

A opção de GeoJSON exige `geopandas` e `pyogrio`, já previstos no `requirements.txt`. Se o SHP tiver nome de coluna de zona diferente dos detectados, use `--campo-zona NomeExatoDoCampo`. A geração **falha** quando não encontra 527 polígonos válidos com CRS declarado.

### Saídas essenciais

| Arquivo | Granularidade e utilização |
| --- | --- |
| `dim_zonas_od2023.csv` | 527 zonas, com 39 municípios e 96 distritos da capital |
| `dim_municipios_od2023.csv` | 39 municípios, código **OD**, diferente do código IBGE |
| `dim_distritos_sp_od2023.csv` | 96 distritos da capital |
| `fato_od_origens_zona_faixa.csv` | Zona de origem × faixa horária; viagens amostrais/expandidas |
| `fato_od_destinos_zona_faixa.csv` | Zona de destino × faixa horária |
| `fato_od_fluxos_zona_faixa.csv` | Zona origem × zona destino × faixa horária |
| `fato_od_municipios_origem_faixa.csv` | Município origem OD × faixa horária |
| `indicadores_zonas_od2023.csv` | 527 linhas com disponibilidade amostral e indicadores para site |
| `resumo_territorial_od2023.json` | Proveniência, totais, avisos e flags de qualidade |
| `geo_zonas_od2023_rmsp.geojson` | **Opcional**: polígonos OD RMSP, quando shape fornecido |
| `geo_zonas_od2023_capital.geojson` | **Opcional**: 343 polígonos da capital |
| `geo_municipios_derivados_zonas_od2023.geojson` | **Opcional**: dissolve das zonas, não limites municipais oficiais |

**Ressalvas**: modo principal OD `12` significa **táxi não convencional / aplicativo**, não apenas Uber; `FE_VIA` expande viagens de passageiros, não contabiliza motoristas; `DISTANCIA` significa **metros em linha reta**, sem deslocamento ocioso ou distâncias viárias. Não cruzar viagens expandidas com uma renda padrão para chamar de lucro regional. Zonas sem amostra têm valor **vazio**, não zero. Não apresentar dados de 2023 como se fossem de 2026.

## Depois desta execução

- Validar arquivos e qualidade com `resumo_territorial_od2023.json`.
- Carregar geometrias no PostGIS, ligar os fatos de viagens a `zona_od_id` e publicar `analytics.od2023_indicadores_zona` (DDL em `db/004_od2023_territorio.sql`). **Ainda não aplicar DDL automaticamente.**
- Acrescentar GeoSampa para **subprefeituras** e recortes próprios da Prefeitura, se quiser navegação interna além do distrito, e comparar limites por relação espacial; a correspondência tabular do Metrô não prova que uma zona está inteiramente dentro de um distrito.
- Ao terminar a OD, revisar `README.md`, `ROADMAP.md`, `docs/ARQUITETURA_DADOS.md`, `docs/INVENTARIO_DADOS.md`, issues e scripts antigos. Evitar exclusões sem checar referências e histórico de execução.

## Fontes oficiais

- Metrô, OD 2023, anexos revisionados 19/02/2025: https://transparencia.metrosp.com.br/dataset/pesquisa-origem-e-destino-2023-anexos/resource/04bd5c3a-1391-4c33-bda7-6feb3d500c16
- Metrô, apresentação da OD 2023: https://www.metro.sp.gov.br/2025/08/29/confira-os-resultados-da-pesquisa-origem-e-destino/
- Prefeitura de SP, correspondência zonas/distritos/municípios: https://prefeitura.sp.gov.br/web/licenciamento/desenvolvimento_urbano/dados_estatisticos/info_cidade/ambiente_construido/limites_territoriais
- GeoSampa (para complementos territoriais): https://novogeosampa.prefeitura.sp.gov.br/

O manifesto em `dados_referencia_od/manifesto_fontes_dimensoes.json` registra o SHA-256 do Excel usado, os totais e a correção explícita da zona 485 (Juquitiba, código OD `80` no Excel, `20` na aba Municípios).
