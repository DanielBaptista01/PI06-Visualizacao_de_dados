# OD 2023 — método de construção territorial e indicadores

## Materiais da equipe

- `Corresp2017_2023_190225.xlsx`: **aba Divisão Administrativa**, linhas 8 a 534; contém 527 zonas, município, distrito e área. A aba `Municipios` fornece os códigos 1–39 usados na OD.
- `Layout_BD_OD2023_190225.xlsx`: dicionário das variáveis dos microdados.
- `Tabelas_Site_OD2023_REV_190225.xlsx`: tabelas publicadas; não é necessária para o ETL de viagens por modo, mas é referência de comparação agregada.
- `dados_limpos/07_ORIGEM_DESTINO.csv`: microdados **filtrados** por `MODOPRIN=12` pelo pipeline já existente no GitHub. O novo script ainda confere o modo por segurança.
- Shapefile OD `Zonas_2023.shp`: contém a geometria do zoneamento oficial 2023 e deve ser versionado em Storage como RAW, não num CSV de teste.

## Dicionário e fórmulas

- `MODOPRIN = 12`: táxi não convencional/aplicativo, não uma amostra identificada exclusivamente como Uber.
- `FE_VIA`: fator de expansão da viagem; viagens expandidas = `SUM(FE_VIA)` para registros válidos. **Não** contagem de condutores/veículos.
- `ZONA_O`, `ZONA_D`: zonas OD da origem e destino (1–527). Não confundir com código IBGE municipal.
- `MUNI_O`, `MUNI_D`: municípios na codificação OD 1–39; podem ser usados na conferência com o município da zona.
- `H_SAIDA`: hora de saída; faixas: 0–5, 6–11, 12–17, 18–23; hora inválida/ausente constitui grupo próprio.
- `DURACAO`: duração da viagem **em minutos**.
- `DISTANCIA`: distância **em linha reta, em metros**. Exibição em km = `DISTANCIA / 1000`.
- Médias por agrupamento: `SUM(valor * FE_VIA) / SUM(FE_VIA)` somente entre registros com a variável preenchida e válida.

## QA e correção explicitada

A zona **485**, identificada como Juquitiba, traz código `80` no campo de município da aba `Divisão Administrativa`; na aba `Municipios`, o código Juquitiba é `20`. Mantivemos o nome original da zona/município e corrigimos o código do **cadastro analítico** para `20`. Os dois códigos e a justificativa estão registrados na coluna `correcao_codigo_municipio` e no manifesto SHA-256. O RAW original não é alterado. A decisão pode ser reavaliada quando houver nova fonte oficial.

Validação da referência preparada: **527** zonas únicas; **39** municípios; **343** zonas em São Paulo (município OD 36); **96** distritos da capital. O script impede processamento de dimensão que viole essas contagens.

## Sem inferências indevidas

1. Viagens OD 2023 ≠ corridas Uber observadas 2026. A OD permite falar em **deslocamentos declarados de táxi não convencional/aplicativo**.
2. O fator de expansão de **pessoas/viagens** não é fluxo de carros nem receita do motorista.
3. Não multiplicar `DISTANCIA` da OD diretamente por custo de rodagem como se fosse trajeto viário ou quilometragem total do motorista.
4. Dados de combustíveis, energia, FIPE e parâmetros de motorista são, inicialmente, **cenários gerais**; só variam por zona se houver fonte geográfica real para a variável.
5. Setores/zonas sem observação do modo 12 na amostra ficam com métricas nulas (sem observação), não demanda zero.
6. Os limites criados por dissolve de zonas servem ao mapa panorâmico, mas não substituem a malha administrativa oficial. Zonas vinculadas a distrito por planilha podem exigir inspeção espacial ao sobrepor camada de distrito.

## Integração futura no Supabase

- Executar `db/004_od2023_territorio.sql` em ambiente controlado com backup.
- Importar as dimensões usando `COPY` com colunas explícitas e respeitando restrições.
- Importar as tabelas `fato_od_*`; converter GeoJSON a MultiPolygon EPSG:4326 no banco com validação PostGIS.
- Implementar consultas: RMSP → município OD (39) → distrito de São Paulo (96) → zona (343 na capital). Mostrar indicadores apenas na granularidade real.
- Integrar cenários econômicos como dimensão independente até existir espacialização validada de custos/receita.

## Próximo ciclo: higiene de repositório

Ao concluir a OD, comparar os scripts novos com os antigos e classificar arquivos: **essenciais**, **legados preservados**, **gerados por pipeline** e **RAW no Storage**. Atualizar `README.md`, `ROADMAP.md`, `docs/INVENTARIO_DADOS.md`, `docs/ARQUITETURA_DADOS.md`, issues e dicionário de campos. Remover outputs de teste do Git de forma seletiva e segura, não apagar checkpoints FIPE nem arquivos com proveniência.
