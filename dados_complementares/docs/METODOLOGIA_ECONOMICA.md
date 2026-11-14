# Metodologia econômica — veículos para aplicativos

**Escopo:** São Paulo (comparação de veículos, tecnologias e perfis de motorista). O objetivo é simular custos e resultado econômico sob hipóteses transparentes — **não identificar lucro efetivamente observado de usuários da Uber**.

## Entradas disponíveis

- **Veículos e preços:** `dados_limpos/08_FIPE_VEICULOS_PARCIAL.csv` (referência novembro/2026), com chaves de versão/ano e preço; coleta parcial.
- **Eficiência:** `dados_limpos/05_INMETRO_VALIDADO.csv` (consumo gasolina/etanol, métricas elétricas, propulsão, versão e linha do catálogo).
- **Preços energéticos:** `03_ANP_PRECOS_CAPITAL_NOV2026.csv` (ANP, 08–14/11/2026) e `02_ANEEL_CENARIO_ENERGIA_SP.csv` (ANEEL/Enel SP residencial).
- **Categorias Uber:** `09_UBER_MODELOS_SP.csv`, com compatibilidade preliminar do ano; não é cadastro de carros ativos.
- **Aluguel:** `17_UBER_MATCH_OFERTAS_SP.csv`, com preços e termos por oferta, sujeito a disponibilidade/validade.
- **Custos:** `dados_config/cenarios_motorista.csv`, `dados_config/cenarios_motorista_pesquisa_2026.csv`, `catalogo_premissas_economicas.csv`, `dados_complementares/etapa19/`, IPVA 2026.

## Granularidade correta

1. **INMETRO:** versão (linha de tabela) × modalidade de energia × consumo. Pode gerar custo energético mesmo sem preço FIPE correspondente.
2. **FIPE:** versão comercial × ano-modelo × mês de preço; o join com INMETRO só é **homologado** com evidência de versão e motorização.
3. **Uber:** marca/modelo/ano mínimo/categoria; compatibilidade preliminar **não** certifica aceitação do veículo pela plataforma.
4. **Perfil motorista:** regime próprio/alugado × km/mês × horas/mês × receitas/despesas, com taxas e contratos explícitos.
5. **OD:** região/zona/faixa horária com demanda descritiva; **não permite estimar renda ou taxa Uber por zona**.

## Cálculo energético

Se o consumo é dado em **km/l**:

`custo_combustivel_rs_km = preco_combustivel_rs_litro / rendimento_km_l`

Para elétrico, se a medida `consumo_energetico_mj_km` for usada como consumo elétrico do veículo:

`consumo_kwh_km ≈ consumo_mj_km / 3,6`

`custo_eletrico_rs_km ≈ consumo_kwh_km × tarifa_rs_kwh / eficiencia_recarga`

A divisão por eficiência de recarga representa **uma hipótese sobre perdas**; verificar a metodologia do indicador INMETRO para não contabilizar duas vezes perdas já embutidas. Tarifa da ANEEL usada no baseline: R$ 0,78938/kWh **sem tributos**; recarga pública deve ser outro cenário. Para PHEV, eventual partilha elétrica/combustão exige proporção assumida e identificada; não chamar o resultado de consumo observado.

`custo_energia_rs_mes = custo_energia_rs_km × km_mes` (quilometragem total operacional, não apenas com passageiro).

## Componentes de custos

| Componente | Cálculo | Observação |
| --- | --- | --- |
| Energia | km/mês × custo energético/km × fração paga | Fração paga depende de contrato para alugado |
| Manutenção | km/mês × provisão/km × fração paga | Média publicada ≠ custo comprovado de cada modelo |
| Pneus | km/mês × provisão/km × fração paga | Desgaste, pneu e condição de via variam |
| Seguro | valor mensal × fração paga | Verificar cobertura para transporte por app e titularidade |
| IPVA | IPVA efetivo anual ÷ 12 × fração paga | Regras e isenções condicionais; FIPE nov/2026 ≠ base venal IPVA 2026 |
| Licenciamento | taxa anual ÷ 12 × fração paga | SP/2026: R$ 174,08 no catálogo; confirmar exercício e responsabilidade |
| Lavagem/celular/outros | despesa mensal definida | Explicitamente hipotética se não observada |
| Depreciação | perda de valor estimada por mês | Só para próprio; ideal usar mesma versão e referências FIPE temporais comparáveis |
| Aluguel | tarifa contratual mensal equivalente | Só alugado; não descontar depreciação do veículo do locatário |
| Financiamento | **não implementado** | Juros e fluxo de caixa do principal exigem módulo próprio |

## Receita e lucro estimado

O campo `receita_plataforma_liquida_rs_mes` representa **recebimentos repassados ao motorista depois das taxas da plataforma, mas antes dos custos operacionais do próprio motorista**. Se o dado de estudo já for *rendimento líquido após combustível e manutenção*, **não alimentá-lo diretamente nesse campo**, para evitar duplicação.

`custo_total_economico = energia + manutencao + pneus + seguro + IPVA + licenciamento + lavagem + celular + outros + depreciacao_ou_aluguel`

`resultado_economico_rs_mes = receita_plataforma_liquida_rs_mes - custo_total_economico`

`receita_equilibrio_rs_km = custo_total_economico / km_mes` e `receita_equilibrio_rs_hora = custo_total_economico / horas_mes` (com horas > 0).

Um **resultado vazio/NULL** indica falta de parâmetros suficientes, não lucro de R$ 0. O motor `economia_completa_pi06.py` bloqueia financiamento e registra `campos_pendentes`. Na primeira execução documentada foram geradas 1.676 linhas de cenário, todas `PARCIAL_PENDENTE` por ausência de receita ou custos.

## Premissas demonstrativas do perfil pesquisado

O arquivo `dados_config/cenarios_motorista_pesquisa_2026.csv` contém, no regime próprio: 3.000 km/mês, 200 horas/mês, manutenção de R$ 0,10/km, pneus de R$ 0,03/km, lavagem R$ 80/mês, celular R$ 50/mês, seguro R$ 400/mês, contribuição de R$ 86,05/mês **apenas para perfil MEI aplicável**, licenciamento R$ 174,08/ano. **A maior parte é cenário referencial, não média para todos os motoristas.** Receita, IPVA individual e depreciação estão vazios.

No aluguel, **não** deixar como zero coberturas desconhecidas de seguro, manutenção, impostos ou pneus. O contrato real define quem paga. Valores de caução não são automaticamente custo operacional; podem afetar fluxo de caixa.

## Comparações que podem aparecer no site

- Custo energético por km e por 3.000 km hipotéticos para versões INMETRO.
- Gasolina versus etanol, combustível versus elétrico residencial e recarga pública (tarifas e vigências explícitas).
- Veículo próprio versus aluguel por contrato, quando se conheçam tarifa, itens incluídos e hipóteses de custo.
- Ponto de equilíbrio e sensibilidade da renda recebida pelo motorista, sem chamar de estimativa observada.
- Preço FIPE **separadamente** enquanto a versão não tiver correspondência INMETRO homologada.

## Erros metodológicos proibidos

- Multiplicar demanda OD por ganho/margem hipotética como se fosse receita territorial observada.
- Atribuir consumo de outro modelo/versão (`DOLPHIN` × `DOLPHIN MINI`, `MUSTANG` × `MACH-E`).
- Tratar ano mínimo Uber como elegibilidade comprovada.
- Usar valores ausentes como zero; misturar bases com períodos diferentes sem rótulo.
- Usar alíquota IPVA universal para todo híbrido/elétrico sem condições legais.
- Confundir rendimento líquido do IBGE com pagamento da plataforma antes das despesas.

## Implementações e SQL

- `modelo_economico.py`: motor de energia e cenários básicos.
- `consolidar_pi06.py`: vínculos candidatos e cenários por INMETRO, sem homologação automática.
- `economia_completa_pi06.py`: próprio/alugado com parcelas de custos, resultado parcial ou completo.
- `integrar_pesquisa_economica.py`: catálogo e perfis pesquisados.
- `db/002_consolidacao_staging.sql`, `db/003_fato_cenarios_motorista.sql`: **esquemas de preparação**, não evidência de carga no Postgres.

Manter versões temporais, links de fonte e identificadores de premissas nos relatórios de publicação.
