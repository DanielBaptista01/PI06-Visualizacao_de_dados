# Mapa interativo — hierarquia e comportamento para o frontend

**Escopo geográfico:** RMSP com 39 municípios; foco no município São Paulo (ID OD 36), subdividido em 96 distritos e 343 zonas OD; as 184 zonas restantes pertencem aos outros 38 municípios. Existem 527 zonas no total.

## Interação sugerida

| Nível | Ação na interface | Conteúdo com fonte |
| --- | --- | --- |
| RMSP | Mostrar 39 municípios | Contorno oficial, nome, total de zonas OD; viagens OD agregadas por origem se presente |
| Município | Clicar no município | Contorno e zonas próprias; no município de SP pode exibir distritos oficiais |
| Distrito de SP | Clicar no distrito | Zonas associadas; métricas da OD por zona, sem inventar diferenças locais |
| Zona OD | Clicar numa zona | Viagens expandidas por faixa, origem/destino e média de duração; distância em linha reta rotulada |
| Comparador de carro | Escolher tecnologia/versão/perfil | Custo energético e gasto/lucro **hipotético**, variando por veículo e premissas, não por zona sem fonte própria |

**A fonte das viagens é OD 2023 (modo 12), não o log da Uber**. Não usar cor de mapa para ilustrar lucro de um motorista por zona se a receita por zona não foi medida. Indicadores econômicos gerais podem aparecer no painel lateral como cenários com destaque de que não são variações geográficas comprovadas.

## Modelo da API (proposta, ainda não implementada)

- `GET /api/od/municipios`
- `GET /api/od/municipios/{municipio_od_id}/zonas`
- `GET /api/od/municipios/36/distritos`
- `GET /api/od/zonas/{zona_od_id}/indicadores?faixa_horaria=...`
- `GET /api/od/zonas/{zona_od_id}/destinos?faixa_horaria=...`
- `GET /api/economia/cenarios?tecnologia=Eletrico&perfil=proprio_base`

Estas rotas são sugestões para a fase backend. Até lá, usar os CSVs e GeoJSONs apenas para prototipação.

## Fontes para limites

- Oficial canônica OD: Shape do Metrô 2023 (zonas, municípios, distritos).
- Prefeitura/GeoSampa: subprefeituras e limites adicionais do município, devidamente versionados; não presumir que códigos/delimitações são os mesmos da OD.
- Códigos do Metrô não devem ser misturados com códigos IBGE ou distritais da Prefeitura sem tabela de correspondência validada.
