# PI06 — Relatório etapa 1.9

Gerado: 2026-11-07T16:19:13.176166+00:00

- Versão de mestres: 20261107T150640Z_fd637316
- Veículos disponíveis: 968
- Ofertas Uber: 56
- Cenários avaliados: 3
- Cenários matematicamente completos: 0
- Lacunas de parâmetros: 32

## Status
A etapa 1.9 fica **estruturada** com fontes e parâmetros. Cenários sem preenchimento não têm lucro calculado.

## Prioridades
1. Usar `dados_complementares/ipva_sp_2026/` como referência tributária; confirmar vínculo do veículo antes de preencher o IPVA anual.
2. Cotar seguro com uso profissional em São Paulo, marcando perfil, período e cobertura.
3. Registrar plano de revisão por km e valores de pneus por dimensão/vida útil; não adotar custo único universal.
4. Capturar tarifa residencial efetiva e/ou tarifa do operador público com data, impostos e cobrança por tempo.
5. Definir remuneração BRL/hora **online**, incluindo períodos sem corrida; não transplantar BRL/hora em corrida.
6. Depreciação exige série histórica comparável do mesmo veículo; FIPE novembro/2026 isolada não fornece taxa anual.
7. Para contrato Uber, marcar explicitamente itens incluídos e não incluídos após leitura da oferta/contrato.

## Fórmulas
- Licenciamento proprietário: 174,08 / 12.
- Seguro, IPVA: valor anual / 12.
- Pneus: jogo de pneus BRL × km/mês / vida útil km.
- Manutenção: BRL/km × km/mês.
- Gasolina: km/mês × R$/litro / km/l.
- Elétrico: km/mês × kWh/km × R$/kWh / (1 − perda_recarga_pct/100).
- Receita: horas **online**/mês × BRL/hora online.
- Resultado líquido **estimado**: receita informada − custos, apenas quando todos os parâmetros obrigatórios estiverem disponíveis.

## Limitações
Estudo Cebrap/Amobitec cobre dados de 2024 e apresenta rendimento líquido mensal para 40 h/semana, não equivalente à receita bruta em hora online; custo do motorista não deve ser confundido com tarifa cobrada ao passageiro. Atualizar valores periodicamente.
