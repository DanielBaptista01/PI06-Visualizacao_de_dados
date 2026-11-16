# PI06 — Visualização final candidata v2.4 · viabilidade econômica do motorista

**Revisão:** 15/11/2026 · **Recorte:** município de São Paulo (343 zonas OD), com ABVE Brasil apenas no contexto histórico.

## Entrega

A v2.4 **preserva a narrativa, os mapas interativos, os filtros, a série ABVE, a mobilidade OD, fluxos e eletropostos da v2.3**, substituindo o simulador genérico por um motor financeiro discriminado. Não sobrescreve scripts Python, dados-mestres, API ou banco de dados do projeto.

O resultado é um **arquivo HTML autossuficiente e offline** criado pelo script `preparar_site_offline.py`. O Python é executado *uma vez* para incorporar os dados; durante a apresentação basta abrir o HTML no navegador. O template `modelo.html` isoladamente **não é a apresentação completa**.

## Instalação sem sobrescrever a v2.3

Copie a pasta `PI06_site_html_v24/` para a **raiz do repositório**, lado a lado com `dados_analiticos`, `dados_limpos`, `dados_relatorios`, `dados_config` e a pasta v2.3 anterior.

No PowerShell, na raiz do repositório e com o ambiente virtual ativado:

```powershell
python -m unittest discover -s .\PI06_site_html_v24\testes -p "test_*.py" -v
python .\PI06_site_html_v24\preparar_site_offline.py
Start-Process .\apresentacao_PI06_capital_v24.html
```

Ou execute `PI06_site_html_v24\GERAR_APRESENTACAO.bat`.

Para publicar a **mesma versão real**, depois de validá-la, no GitHub Pages configurado para `main` / `docs`:

```powershell
python .\PI06_site_html_v24\preparar_site_offline.py --saida .\docs\index.html
# Opcional: preservar o snapshot desta versão
Copy-Item .\docs\index.html .\docs\v24.html
git add PI06_site_html_v24 docs/index.html docs/v24.html
git commit -m "feat: simulacao economica completa v2.4"
git push
```

Antes do `git add`, verifique que o HTML contém apenas fontes **públicas**, nunca `.env`, credenciais ou informações pessoais de motoristas. O script não grava no Supabase.

## Cenário econômico: campos disponíveis

| Tema | O que o visitante configura | Tratamento |
|---|---|---|
| Recebimento | R$/mês recebido **após a taxa da plataforma**, antes das despesas | Hipótese, R$ 8.000 é exemplo, não média observada |
| Trabalho | Km operacionais e horas online/mês | Hipóteses, defaults 3.000 km e 200 h |
| Veículo | INMETRO: marca, modelo, versão e modalidade | Consumo técnico; não equivale a elegibilidade Uber ou FIPE homologada |
| Combustão / flex | Preço da gasolina ou etanol em R$/l | Média ANP capital, semana 08–14/11/2026, editável |
| Elétrico | Tarifa residencial e recarga pública; parcela carregada fora | Tarifa-base ANEEL **sem tributos**; referência pública é mediana estadual, não preço de um posto |
| Híbrido convencional | Modalidade gasolina ou etanol e consumo próprio INMETRO | Não adiciona recarga externa; recuperação energética já está refletida no consumo homologado |
| Híbrido plug-in | % dos km em modo elétrico e % a combustível | Se faltar consumo da mesma versão, exige valor de consumo elétrico informado pelo usuário; sem energia “grátis” |
| Próprio | Depreciação mensal, IPVA efetivo, seguro, manutenção, pneus | Compra à vista não é somada integralmente como custo do mês; pode estimar depreciação pelo preço, residual e vida útil |
| FIPE | Busca manual de marca/modelo/ano, apenas referência opcional | Só usa preço como hipótese de compra após confirmação humana; não cria vínculo FIPE–INMETRO |
| Alugado | Mensalidade, km inclusos, excedente, coberturas contratadas | Uber Match é snapshot; precisa confirmar aplicabilidade, limite de km e itens incluídos |
| Outros | Lavagem, celular, reparos imprevistos, outras despesas, contribuição MEI aplicável | Premissas editáveis; campos ausentes bloqueiam resultado |

## Fórmulas de referência

- **Combustível:** `custo/km = custo/km INMETRO no cenário-base × (preço escolhido / preço ANP-base)`.
- **Elétrico:** `custo/km = custo/km INMETRO no cenário-base × (tarifa ponderada escolhida / tarifa ANEEL-base)`, em que `tarifa ponderada = (1 − parcela pública) × tarifa residencial + parcela pública × tarifa pública`.
- **Plug-in:** `custo/km = parcela de km a combustível × custo/km combustível + parcela de km elétricos × custo/km elétrico`. É um cenário de uso, não uma média observada. Sem referência elétrica da mesma versão, pode-se usar kWh/km declarados como hipótese, assumindo 90% de eficiência de recarga para a energia comprada. O indicador INMETRO já precificado não recebe essa perda de novo.
- **Manutenção e pneus:** provisões `R$/km × km/mês`. **Reparos imprevistos** são uma provisão separada.
- **IPVA e licenciamento:** valores efetivos `R$/ano ÷ 12`, sem presumir isenção para híbridos/elétricos.
- **Próprio:** depreciação mensal informada ou `(preço de compra − valor residual estimado) / meses de uso`. Preço total de compra não é somado de novo.
- **Alugado:** mensalidade + `max(0, km do mês − km inclusos) × valor por km excedente`, quando há limite contratual. Caução é desembolso inicial/garantia, não despesa mensal automaticamente.
- **Custos totais:** energia + regime (aluguel ou depreciação) + km excedentes + manutenção + pneus + seguro + IPVA/12 + licenciamento/12 + lavagem + celular + reparos + outros + contribuição MEI se aplicável.
- **Resultado econômico simulado = recebimento após plataforma − custos totais**. Ponto de equilíbrio = custos totais ÷ km ou ÷ horas. O resultado pode ser negativo.

**Condição de cálculo:** os custos devem estar informados ou explicitamente cobertos no contrato, os limites de km conhecidos ou assumidos ilimitados e o visitante deve confirmar que as premissas são completas. Caso contrário, o painel mostra subtotal e pendências, **sem criar “lucro zero”**.

**Custo econômico ≠ fluxo de caixa:** a depreciação representa desgaste econômico, não necessariamente dinheiro saindo naquele mês; financiamento, juros, entrada e fluxo de caução não estão modelados. Também não estão medidos demanda individual, horas ociosas ou tarifas Uber por zona. Não concluir lucro local observado.

## Comparação A × B

Selecione carro, modalidade e regime, complete os custos e clique em **Salvar cenário A**. Altere o regime e/ou veículo, configure os valores, clique em **Salvar cenário B**. O site mostra os resultados e a diferença somente quando **ambos têm todos os custos declarados e a mesma quilometragem e receita**. O visitante consegue testar carro próprio vs. alugado ou elétrico vs. gasolina sem inferir rentabilidade regional real.

## Arquivos necessários na raiz do repositório

- `dados_analiticos/cenarios_2026/` (oito CSVs e manifesto com SHA-256),
- `dados_relatorios/territorio_od2023/geo_zonas_od2023_rmsp.geojson` (527 zonas; 343 na capital),
- `dados_relatorios/territorio_od2023/geo_municipios_derivados_zonas_od2023.geojson`,
- `dados_limpos/10_OPEN_CHARGE_MAP_SP.csv`,
- `dados_limpos/03_ANP_PRECOS_CAPITAL_NOV2026.csv`,
- `dados_limpos/02_ANEEL_CENARIO_ENERGIA_SP.csv`,
- `dados_complementares/etapa19/cotacoes.csv`,
- `dados_config/cenarios_motorista_pesquisa_2026.csv`.

São carregados quando disponíveis: `dados_limpos/17_UBER_MATCH_OFERTAS_SP.csv` para locações, `dados_limpos/08_FIPE_VEICULOS_PARCIAL.csv` para consulta de preços **não vinculados automaticamente**, séries ABVE, contexto SENATRAN e outras fontes da versão anterior.

Se os GeoJSONs reais estiverem em outro lugar, use `--geo` e `--geo-municipios`. Ao mudar um CSV analítico, recalcule o manifesto antes de gerar o HTML, pois o gerador rejeita SHA-256 divergente.

## Validação realizada

- **18 testes Python unitários** (16 herdados v2.3 + 2 financeiros de fontes/template), sem chamadas de rede.
- **Cenários de navegador automatizados** (Chromium; 1400, 768, 390, 360 e 320px): próprio, aluguel, limites/km excedente, recarga pública, híbrido convencional, plug-in, custos ausentes, cálculo negativo e comparação A/B, sem rolagem horizontal.
- **Integração do gerador** com 527 geometrias sintéticas, 343 polígonos clicáveis e atualização do mapa em computador e celular; snapshot HTML construído com sucesso.

**Ainda pendente para fechar a entrega:** geração e inspeção no computador da equipe com os CSVs e GeoJSONs reais; revisão dos resultados por mais de uma pessoa e verificação da versão publicada. A prévia HTML opcional contém apenas dados reduzidos e um veículo plug-in *sintético*; **não a publique como trabalho final**.

## Critério de “final candidata”

A versão v2.4 pode ser marcada **candidata à entrega** quando: HTML real produzido, mapa com 343 zonas selecionáveis, simulador próprio e alugado validado, valores de FIPE/ANP/ANEEL conferidos, premissas nomeadas, resultado não apresentado como lucro observado, revisão do Daniel incorporada e HTML publicado/aberto também no celular. Atualizações seguintes podem ser registradas como v2.4.1 sem apagar a versão anterior.
