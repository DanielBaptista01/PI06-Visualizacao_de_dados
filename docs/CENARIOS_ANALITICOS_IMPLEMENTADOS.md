# Cenários analíticos — contrato materializado para o PI06

## Estado

Implementação Python pronta para ser executada nos dados reais; validação de integração testada com fixtures sintéticas. A carga no Supabase/PostGIS e a API **não** estão concluídas. Scripts e documentação do repositório anterior permanecem válidos.

## Fluxo de dados

```text
integrar_od2023.py            consolidar_pi06.py            economia_completa_pi06.py
    |                              |                                |
 indicadores_zonas         fato_cenarios_inmetro        fato_cenarios_motorista
 fato_od_fluxos                    |                                |
    |                              |                                |
    +------------------------------+--------------------------------+
                                   |
                         gerar_cenarios_analiticos.py
                                   |
         +-------------------------+----------------------------+
         |                                                      |
  painel_od_zonas/municipios/distritos/top_destinos                     painel_energia/motorista
         |                                                      |
  filtro territorial                                  filtros perfil/tecnologia
         +---------------------- UI ------------------------------+
```

## Perguntas analíticas e fonte

| Questão | Produto | O que é válido concluir |
|---|---|---|
| Onde a OD 2023 identificou mais saídas e chegadas de táxi não convencional/app? | `painel_od_zonas.csv` | Fluxo **expandido na pesquisa**, não corridas de uma plataforma |
| Quais destinos aparecem na amostra por faixa horária? | `painel_od_top_destinos.csv` | Destinos amostrais, não rotas viárias |
| Qual versão INMETRO tem menor custo técnico de energia em determinada modalidade? | `painel_energia_inmetro.csv` | Comparação de cenários energéticos usando premissas ANP/ANEEL; versão INMETRO, não FIPE |
| Quais custos do motorista já podemos quantificar? | `painel_motorista_custos.csv` | Subtotal das parcelas conhecidas com lacunas explícitas |
| Como mudaria o resultado se o motorista recebesse R$ 6/8/10 mil antes dos seus custos? | `painel_sensibilidade_receita.csv` | **Só** se todos os custos estiverem preenchidos; hipótese didática, não média real |

## Regras SQL e API

- `db/005_cenarios_analiticos.sql` define tabela de premissas e views com a mesma separação por domínio. O SQL **não** promove dados FIPE/INMETRO não homologados a vínculos confirmados.
- **Mapa:** zona/município/distrito/horário de OD. **Comparador:** INMETRO + perfil e receita hipotética. São filtros independentes.
- Para o mapa, consultar uma zona ou limitar número de destinos; nunca enviar dezenas de milhares de geometrias sem simplificação apropriada.
- Para o comparador, exigir filtros de perfil/modalidade/tecnologia e paginação antes de expor publicamente.
- Expor metadados: `fonte`, `natureza_dado`, referência temporal, premissas e `campos_pendentes`.
- Antes de habilitar a API pública: validar índices, `RLS`/grants, chaves, geometrias válidas, `COUNT(*)` e conformidade com manifesto SHA-256.

## Limites matemáticos

`subtotal_custos_conhecidos = SUM(componentes numéricos disponíveis)`, identificado como subtotal, **não custo total**.

`resultado_economico_simulado = recebimento_hipotético_após_taxas_plataforma - custo_total` **somente quando** todos os custos têm valores e as premissas são coerentes.

A renda divulgada pelo IBGE após despesas **não** pode alimentar diretamente o recebimento antes das despesas. A quilometragem operacional hipotética da economia não equivale à distância em linha reta da OD.

## Como registrar qualidade

| Natureza | Significado |
|---|---|
| `AMOSTRAL_EXPANDIDO` | Resultado da amostra OD com FE_VIA e ressalvas |
| `SIMULADO_ENERGIA` | Resultado técnico INMETRO com preços/eficiência assumidos |
| `SIMULADO_COM_PREMISSAS` | Cenário econômico de motorista, possivelmente incompleto |
| `HIPOTESE_DIDATICA` | Recebimento mensal ilustrativo sem fonte observacional |
| `SIMULACAO_HIPOTETICA` | Sensibilidade financeira, só completa se todos os custos estão presentes |

## Não inferir

- Participação da Uber nas 1.041.875,01 viagens expandidas modo 12;
- Número de motoristas disponíveis por zona;
- Receita Uber por corrida ou por zona;
- Distância rodoviária a partir de linha reta OD;
- Elegibilidade real de versões FIPE para todas as categorias Uber;
- Preço FIPE da versão INMETRO sem homologação;
- IPVA universal para todos os híbridos/elétricos.
