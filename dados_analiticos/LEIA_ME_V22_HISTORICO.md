# PI06 — Site interativo v2.2 (São Paulo capital)

## O que muda em relação à v2

- **Recorte principal exclusivo do município de São Paulo**: 343 zonas OD e 96 distritos. Não há seletor de Barueri, Guarulhos ou demais municípios da RMSP.
- **Região**: Todas as regiões, Centro, Norte, Sul, Leste e Oeste. As regiões são baseadas na tabela da Prefeitura de São Paulo/SMUL (2025), relacionando os 96 distritos da OD a suas regiões oficiais.
- **Distrito**: opções ajustadas à região escolhida.
- **Zona específica**: Todas as zonas do recorte ou uma zona OD, com navegação para ela.
- **Busca digitável**: procura por número OD, nome de zona, distrito ou região da capital, mesmo quando outro filtro estiver ativo. Clique no resultado ou pressione **Enter**.
- **Clique direto no mapa**: qualquer polígono pode ser selecionado, até os atenuados por filtro. O clique prevalece sobre a seleção prévia, sincroniza Região → Distrito → Zona e atualiza o painel lateral. Arrastar/zoom continuam possíveis sem interceptar o clique.
- **Painel lateral**: quando não há uma zona selecionada, mostra resumo do recorte (cidade, região ou distrito); ao escolher uma zona, apresenta exclusivamente seus indicadores OD e contexto municipal SENATRAN.
- **Fluxos**: o seletor do site inclui apenas origens na capital e, para a lista de destinos, apenas destinos da capital presentes no **top 5 original** (o ranking completo de todos os fluxos internos exigiria a tabela-base não reduzida).
- **Eletropostos**: apenas pontos cadastrados com cidade São Paulo, em enquadramento da capital. O status não comprova funcionamento em tempo real.

## Instalar sem substituir a v2

1. Extraia `PI06_site_html_v22/` **na raiz do repositório** PI06, ao lado de `dados_analiticos/`, `dados_limpos/` e `dados_relatorios/`.
2. Confira os testes (com o `.venv-2` ativado):

```powershell
python -m unittest discover -s .\PI06_site_html_v22\testes -p "test_*.py" -v
```

3. Gere a apresentação final incorporando os CSVs e GeoJSONs reais:

```powershell
python .\PI06_site_html_v22\preparar_site_offline.py
```

4. Abra o resultado:

```powershell
Start-Process .\apresentacao_PI06_capital_v22.html
```

Também há o atalho `PI06_site_html_v22/GERAR_APRESENTACAO.bat`.

**No dia da apresentação:** basta abrir `apresentacao_PI06_capital_v22.html` no navegador e pressionar **F11**. Python só é necessário **para gerar** o arquivo, não para apresentá-lo.

## Prévia versus apresentação final

- `PI06_site_html_v22/index.html` é uma **prévia parcial** com apenas dois registros territoriais reais e uma imagem de referência. **Ela não é o mapa interativo completo**.
- `apresentacao_PI06_capital_v22.html` é gerado no seu computador com **343 polígonos oficiais clicáveis**, indicadores OD e painéis existentes. O arquivo único funciona offline e não exige Supabase ou servidor.
- A geração **não altera** os CSVs anteriores nem os módulos Python do pipeline. Se as bases mudaram desde o manifesto, o programa interrompe com aviso de SHA-256 divergente para evitar apresentar versões incompatíveis.

## Dados e limites

- A **OD 2023** (`MODOPRIN=12`) não equivale a corridas exclusivas Uber. O total de viagens com origem na capital considera todos os destinos da pesquisa; o ranking de destinos do HTML foi filtrado para as zonas da capital.
- Sem amostra na zona **não significa zero de viagens**.
- A **SENATRAN** informa frota por categoria de combustível na **escala municipal**, incluindo tipos de veículos que não são carros de aplicativo. **Não existe frota elétrica/híbrida/gasolina por zona OD** nesta base.
- A **ABVE** tem série histórica 2022–2026 no nível **Brasil**; serve como contexto do problema, não como série de vendas da capital. A **FIPE** é recorte parcial de preços de novembro de 2026, não evolução histórica de preços.
- As cinco regiões agregadas correspondem à fonte oficial da Prefeitura, mas a atribuição das zonas OD é feita pelo **nome do distrito**, sem alterar os limites geométricos originais de 2023.

**Fonte oficial da divisão territorial de 2025:**
https://prefeitura.sp.gov.br/documents/d/licenciamento/2025_regioes_subprefeituras_e_distritos_municipais-1-

## Estrutura

```text
PI06_site_html_v22/
  modelo.html                       # Interface e interações
  preparar_site_offline.py          # Gera um único HTML final a partir das bases existentes
  regioes_sp_2025.csv               # 96 distritos → 5 regiões da capital
  index.html                        # Prévia parcial, NÃO usar como apresentação final
  GERAR_APRESENTACAO.bat
  assets/od2023_mapa_referencia.jpg # Imagem da prévia
  testes/                           # Testes automatizados
```

**Nota:** a geração do HTML final exige o arquivo já produzido pelo projeto:
`dados_relatorios/territorio_od2023/geo_zonas_od2023_rmsp.geojson`. Ele é validado no total de 527 zonas originais, mas apenas as 343 zonas paulistanas são desenhadas no mapa final.
