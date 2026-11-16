# PI06 — Site interativo v2.3 · revisão do Daniel + responsividade

## Objetivo da atualização

Esta versão **mantém a v2.2** (evolução ABVE, mapa OD, fluxos, energia, economia, recarga e simulador) e acrescenta a seção **07 — Teste da hipótese do PI06**, pedida na transcrição do colega.

A pergunta é: **"Qual configuração de veículo poderia ser mais vantajosa sob premissas iguais, considerando o contexto de uma região da cidade?"** Não chamamos o resultado de **lucro regional comprovado**, porque **não temos rendimento por motorista/veículo/zona**, nem relação válida que converta viagens OD em lucro individual.

### Alterações da v2.3

| Mudança | Funcionalidade | Fonte / limite |
|---|---|---|
| **Quarto mapa** | 343 zonas OD da capital com clique direto, zoom e painel lateral; filtros de região, distrito e busca por nome/número | OD 2023 (modo 12) |
| **Duas camadas no mapa** | Intensidade de origens OD / pontos OCM cadastrados por zona | OD/OCM em períodos diferentes; não prever demanda por recarga |
| **Vínculo espacial OCM × zona** | Verifica os pontos por coordenada **dentro do polígono** (inclusive buracos em MultiPolygon). Conta quantidade cadastrada e status reportado "Operational" | Status de cadastro não é disponibilidade em tempo real |
| **Comparador de três configurações** | Selecione um veículo de cada grupo (gasolina/flex, híbrido, elétrico), modalidade e km mensais; veja custo energético comparável | INMETRO + preços-base ANP/ANEEL do cenário; sem garantia de elegibilidade Uber |
| **Resultado hipotético, opcional** | Informe as **demais despesas integrais para cada um dos 3 carros** + confirme que elas incluem todos os custos; sistema calcula resultado mensal com a mesma hipótese de recebimento | Não é renda observada, nem estima lucro por zona |
| **Seleções sincronizadas** | Escolha zona no mapa 4 ↔ mapa principal; ao abrir o mapa principal, o recorte já está selecionado | Interação sem serviços externos |
| **Celular/tablet** | Menu hambúrguer, painéis empilhados, ajustes 320px–1400px, botões de zoom maiores, campos adaptativos | HTML/CSS/JavaScript responsivo |

### Regra da análise

- Se **faltam despesas complementares**, a classificação identifica **o menor custo de energia entre as versões escolhidas**, não o veículo de maior lucro.
- Quando o usuário preenche todos os valores de **demais despesas mensais** e marca a declaração de completude, a classificação passa a apresentar **maior resultado econômico simulado**, calculado como `recebimento hipotético − (custo energético + demais despesas)`.
- As informações da OD e os registros OCM **mudam com o território selecionado**, mas o custo energético/km do veículo **não muda** sem uma fonte de custo energético que varie comprovadamente por região. Assim, o quarto mapa testa o argumento do colega **sem fabricar recomendação de veículo por bairro**.
- O modelo usa a classificação já simplificada do PI06: `Gasolina` (inclui etanol/flex), `Híbrido` e `Elétrico`.

## Instalar no repositório sem apagar a versão anterior

Extraia `PI06_site_html_v23/` **na raiz** do repositório `PI06-Visualizacao_de_dados`, ao lado de `dados_analiticos/`, `dados_limpos/` e `dados_relatorios/`.

No PowerShell, com `.venv-2` ativado:

```powershell
python -m unittest discover -s .\PI06_site_html_v23\testes -p "test_*.py" -v
python .\PI06_site_html_v23\preparar_site_offline.py
Start-Process .\apresentacao_PI06_capital_v23.html
```

O segundo comando gera o **HTML completo e independente**, incluindo os 343 polígonos OD, indicadores, geolocalização dos eletropostos e funcionamento do comparador. Os arquivos ficam embutidos no HTML; não é necessário Supabase ou Python ao abrir a apresentação.

**Alternativa:** abra `PI06_site_html_v23/GERAR_APRESENTACAO.bat` no Windows; ele localiza o Python e gera/abre o arquivo.

### Publicar no GitHub Pages do MESMO repositório

Depois de verificar o HTML completo com os dados reais:

```powershell
python .\PI06_site_html_v23\preparar_site_offline.py --saida .\docs\index.html
```

Com GitHub Pages configurado para `main` + `/docs`, `docs/index.html` será a versão principal. Você também pode preservar versões adicionais:

```powershell
Copy-Item .\docs\index.html .\docs\v23.html
# Depois de alterar dados/código e gerar nova versão, atualize somente o index.html.
git add PI06_site_html_v23 docs/index.html docs/v23.html
git commit -m "feat: adiciona mapa de decisao e site responsivo v2.3"
git push
```

**Atenção:** GitHub Pages é público. Antes do `git add`, confirme que `index.html` não contém dados privados, tokens ou credenciais — o gerador usa somente CSVs e geometrias de visualização.

### Fontes exigidas para construir a apresentação completa

- `dados_analiticos/cenarios_2026/` com os oito CSVs e `manifesto_cenarios_analiticos.json` **consistentes nos SHA-256**.
- `dados_relatorios/territorio_od2023/geo_zonas_od2023_rmsp.geojson` com 527 zonas originais, das quais 343 na capital.
- `dados_relatorios/territorio_od2023/geo_municipios_derivados_zonas_od2023.geojson` (recomendado, para contorno municipal).
- `dados_limpos/10_OPEN_CHARGE_MAP_SP.csv` para infraestrutura.
- `dados_padronizados/11_ABVE_VENDAS_TECNOLOGIA_BRASIL_MENSAL.csv`, `dados_limpos/06_SENATRAN_COMBUSTIVEL_SP.csv` e `dados_limpos/08_FIPE_VEICULOS_PARCIAL.csv` para contexto histórico e municipal.

Se a localização dos GeoJSONs for diferente, use:

```powershell
python .\PI06_site_html_v23\preparar_site_offline.py --geo "CAMINHO\Zonas_2023.geojson" --geo-municipios "CAMINHO\Municipios_OD.geojson"
```

## O que foi testado e o que ainda falta verificar

**Confirmado neste pacote:** 16 testes unitários, verificação de sintaxe JavaScript e interação no Chromium com fixtures sintéticas em desktop 1400px, tablet 768px e celulares 390px, 360px e 320px. Clique em zona, busca, atualização de comparação, declaração de custos, menu móvel e ausência de rolagem horizontal foram testados.

**Pendente no computador do projeto:** executar o script com os CSVs/GeoJSONs **reais** e verificar visualmente Jabaquara, Itaim Bibi, Santo Amaro, dados OCM e uma seleção de Corolla Cross (se esta versão existir no INMETRO do conjunto) frente a outros carros. Também vale testar o HTML completo em celulares reais e navegador móvel antes da publicação.

**Não entregamos um `index.html` de demonstração com mapa em imagem estática.** A apresentação real é `apresentacao_PI06_capital_v23.html`, **gerada localmente**, ou `docs/index.html`, gerada com a opção `--saida` acima. O HTML `modelo.html` é um template e não deve ser publicado sozinho.

### Bônus de revisão para o roteiro em sala

Na nova seção **"Qual veículo pode compensar em cada região?"**, demonstre duas áreas diferentes, alternando a camada OD e a camada OCM, e mostre que **a opção tecnicamente mais barata em energia pode continuar igual**. Em seguida, preencha hipóteses de despesas completas para demonstrar como o resultado pode mudar. Essa distinção é a contribuição científica do PI06: uma hipótese pode ser **apoiada ou contrariada sob condições explícitas**, não "comprovada" por um mapa sem dados de renda.
