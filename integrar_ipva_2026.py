"""PI06 — Consolidação não destrutiva do IPVA paulista 2026.

Entrada: dados_padronizados/18_IPVA_SP_VALORES_VENAIS_2026.csv
Saídas: dados_complementares/ipva_sp_2026/ (nunca modifica as fontes).

Os benefícios para híbridos e locadoras NÃO são concedidos automaticamente.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

FONTE = Path('dados_padronizados/18_IPVA_SP_VALORES_VENAIS_2026.csv')
DESTINO = Path('dados_complementares/ipva_sp_2026')
ARQUIVO_MESTRE = 'veiculos/dim_modelos_versoes_inmetro.csv'
COLUNAS = {'exercicio_ipva', 'mes_base', 'categoria_codigo', 'categoria',
           'linha_tabela', 'descricao_marca_modelo', 'codigo_ipva',
           'codigo_complemento', 'ano_fabricacao_modelo_tabela',
           'valor_venal_reais', 'pagina_pdf', 'arquivo_fonte'}
URL_LEI = 'https://legislacao.fazenda.sp.gov.br/Paginas/lei13296.aspx'
URL_ISENCAO = 'https://legislacao.fazenda.sp.gov.br/Paginas/Portaria-SRE-94-de-2024.aspx'
URL_LOCADORA = 'https://portal.fazenda.sp.gov.br/servicos/ipva/Paginas/Pedido-de-cadastramento-.aspx'


def normalizar(valor: object) -> str:
    if pd.isna(valor):
        return ''
    texto = unicodedata.normalize('NFKD', str(valor))
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    return ' '.join(re.sub(r'[^A-Z0-9]+', ' ', texto.upper()).split())


def ler_fonte(raiz: Path) -> tuple[pd.DataFrame, Path]:
    origem = raiz / FONTE
    if not origem.is_file():
        raise FileNotFoundError(f'CSV do IPVA não encontrado: {origem}')
    dados = pd.read_csv(origem, dtype={'codigo_ipva': 'string', 'codigo_complemento': 'string'}, low_memory=False)
    ausentes = COLUNAS - set(dados.columns)
    if ausentes:
        raise ValueError(f'Colunas obrigatórias ausentes: {sorted(ausentes)}')
    if dados.empty:
        raise ValueError('A fonte IPVA está vazia.')
    for coluna in ('valor_venal_reais', 'exercicio_ipva', 'ano_fabricacao_modelo_tabela', 'pagina_pdf'):
        dados[coluna] = pd.to_numeric(dados[coluna], errors='raise')
    if dados[list(COLUNAS)].isna().any().any():
        raise ValueError('A fonte tem campos obrigatórios nulos; revisar antes do processamento.')
    if not dados['exercicio_ipva'].eq(2026).all() or not dados['mes_base'].eq('2025-09').all():
        raise ValueError('Exercício ou mês-base diferente do esperado (2026 / 2025-09).')
    if dados['valor_venal_reais'].le(0).any():
        raise ValueError('Existem valores venais menores ou iguais a zero.')
    chave = ['exercicio_ipva', 'categoria_codigo', 'codigo_ipva', 'codigo_complemento', 'ano_fabricacao_modelo_tabela']
    if dados.duplicated(chave).any():
        raise ValueError('Encontradas chaves de valor venal duplicadas.')
    return dados, origem


def calcular_base(dados: pd.DataFrame) -> pd.DataFrame:
    resultado = dados.copy()
    automovel = resultado['categoria_codigo'].eq('A')
    resultado['tipo_calculo'] = 'nao_calculado_outra_categoria'
    resultado.loc[automovel, 'tipo_calculo'] = 'referencia_automovel_4pct_sem_beneficio'
    resultado['aliquota_base_automovel_pct'] = pd.Series(pd.NA, index=resultado.index, dtype='Float64')
    resultado.loc[automovel, 'aliquota_base_automovel_pct'] = 4.0
    resultado['ipva_base_automovel_brl'] = pd.Series(pd.NA, index=resultado.index, dtype='Float64')
    resultado.loc[automovel, 'ipva_base_automovel_brl'] = (resultado.loc[automovel, 'valor_venal_reais'] * 0.04).round(2)
    # Não se aplica a todos: é apenas comparação condicionada ao cadastro de locadora.
    resultado['ipva_locadora_hipotese_1pct_brl'] = pd.Series(pd.NA, index=resultado.index, dtype='Float64')
    resultado.loc[automovel, 'ipva_locadora_hipotese_1pct_brl'] = (resultado.loc[automovel, 'valor_venal_reais'] * 0.01).round(2)
    resultado['status_isencao_hibrido_2026'] = 'nao_avaliado_requer_comprovacao_tecnica_e_cadastral'
    resultado['ipva_isencao_hibrido_confirmada_brl'] = pd.Series(pd.NA, index=resultado.index, dtype='Float64')
    resultado['observacao'] = 'Cenário de referência, não equivale ao débito efetivo de um RENAVAM.'
    return resultado


def localizar_mestre(raiz: Path) -> Path | None:
    ponteiro = raiz / 'dados_mestres/atual.json'
    if not ponteiro.exists():
        return None
    info = json.loads(ponteiro.read_text(encoding='utf-8-sig'))
    pasta = info.get('pasta')
    if not isinstance(pasta, str) or not pasta.startswith('execucoes/') or '..' in Path(pasta).parts:
        raise ValueError('Ponteiro dados_mestres/atual.json inválido.')
    caminho = raiz / 'dados_mestres' / pasta / ARQUIVO_MESTRE
    return caminho if caminho.is_file() else None


def candidatos_inmetro(dados: pd.DataFrame, mestre_path: Path | None) -> pd.DataFrame:
    colunas = ['linha_inmetro', 'marca', 'modelo', 'versao', 'qtd_descricoes_ipva_candidatas',
               'qtd_codigos_ipva_candidatos', 'codigos_ipva_candidatos', 'status_vinculo']
    if mestre_path is None:
        return pd.DataFrame(columns=colunas)
    mestre = pd.read_csv(mestre_path, low_memory=False)
    if not {'marca', 'modelo', 'versao'}.issubset(mestre.columns):
        raise ValueError(f'Colunas ausentes no mestre INMETRO: {mestre_path}')
    automoveis = dados[dados['categoria_codigo'].eq('A')].copy()
    automoveis['descricao_norm'] = automoveis['descricao_marca_modelo'].map(normalizar)
    grupos: dict[str, list[tuple[str, str]]] = {}
    for item in automoveis[['descricao_norm', 'codigo_ipva']].drop_duplicates().itertuples(index=False):
        descricao = item.descricao_norm
        # A descrição oficial pode começar com I/ ou IMP/.
        segmentos = descricao.split()
        prefixo = 1 if segmentos and segmentos[0] in {'I', 'IMP'} else 0
        marca = segmentos[prefixo] if len(segmentos) > prefixo else ''
        grupos.setdefault(marca, []).append((descricao, str(item.codigo_ipva)))
    saida = []
    for pos, registro in enumerate(mestre.itertuples(index=False), start=1):
        r = registro._asdict()
        marca, modelo = normalizar(r['marca']), normalizar(r['modelo'])
        versao = normalizar(r['versao'])
        # Correspondência de texto parcial: apenas candidato, nunca merge confirmado.
        candidatas = [(desc, cod) for desc, cod in grupos.get(marca, [])
                      if modelo and re.search(r'(?<!\w)' + re.escape(modelo) + r'(?!\w)', desc)]
        codigos = sorted({cod for _desc, cod in candidatas})
        saida.append({'linha_inmetro': pos, 'marca': r['marca'], 'modelo': r['modelo'],
                      'versao': r['versao'], 'qtd_descricoes_ipva_candidatas': len(set(x[0] for x in candidatas)),
                      'qtd_codigos_ipva_candidatos': len(codigos),
                      'codigos_ipva_candidatos': '|'.join(codigos),
                      'status_vinculo': 'sem_candidato' if not codigos else 'candidato_nao_confirmado'})
    return pd.DataFrame(saida, columns=colunas)


def executar(raiz: Path) -> None:
    fonte, caminho = ler_fonte(raiz)
    tabela = calcular_base(fonte)
    mestre = localizar_mestre(raiz)
    cobertura = candidatos_inmetro(fonte, mestre)
    relatorio = pd.DataFrame([
        {'assunto': 'IPVA geral automóvel', 'condicao': 'Categoria A, sem benefício', 'situacao': 'calculado_cenario_base', 'fonte': URL_LEI},
        {'assunto': 'Híbrido com etanol/flex', 'condicao': 'Valor limite atualizado e requisitos técnicos de 40 kW / 150 V, e cadastro', 'situacao': 'pendente_validacao_por_versao', 'fonte': URL_ISENCAO},
        {'assunto': 'Veículo elétrico', 'condicao': 'Sem isenção estadual universal por ser elétrico', 'situacao': 'nao_presumir_isencao', 'fonte': URL_LEI},
        {'assunto': 'Locadora', 'condicao': 'Benefício de 1% depende de locadora habilitada e veículo elegível', 'situacao': 'hipotese_nao_confirmada', 'fonte': URL_LOCADORA},
        {'assunto': 'Veículo novo 0 km', 'condicao': 'Base de cálculo difere da tabela de usados', 'situacao': 'fora_do_escopo_desta_base', 'fonte': URL_LEI},
        {'assunto': 'Outras categorias B-F', 'condicao': 'Regras específicas por tipo e combustível', 'situacao': 'nao_calculado', 'fonte': URL_LEI},
        {'assunto': 'Relacionamento INMETRO', 'condicao': 'Descrições podem ser abreviadas, com versões distintas', 'situacao': 'apenas_candidatos', 'fonte': 'dados_mestres/atual.json'},
    ])
    destino = raiz / DESTINO
    destino.mkdir(parents=True, exist_ok=True)
    tabela.to_csv(destino / '18_IPVA_SP_CENARIOS_BASE_2026.csv', index=False, encoding='utf-8-sig')
    cobertura.to_csv(destino / '18_IPVA_INMETRO_CANDIDATOS.csv', index=False, encoding='utf-8-sig')
    relatorio.to_csv(destino / '18_IPVA_REGRAS_E_PENDENCIAS.csv', index=False, encoding='utf-8-sig')
    sha = hashlib.sha256(caminho.read_bytes()).hexdigest()
    manifesto = {'gerado_em_utc': datetime.now(timezone.utc).isoformat(),
                 'fonte': str(FONTE), 'sha256_fonte': sha,
                 'total_valores_venais': len(tabela),
                 'total_automoveis_com_cenario_base': int(tabela['ipva_base_automovel_brl'].notna().sum()),
                 'total_candidatos_inmetro_com_correspondencia_textual': int(cobertura['qtd_codigos_ipva_candidatos'].gt(0).sum()) if not cobertura.empty else 0,
                 'tabela_mestre_inmetro': str(mestre.relative_to(raiz)) if mestre is not None else None,
                 'isencoes_automaticamente_confirmadas': 0,
                 'nota': 'Apenas cenários tributários e vínculos candidatos; não representa cobrança individual.'}
    (destino / 'manifesto_ipva_2026.json').write_text(json.dumps(manifesto, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"[OK] Valores venais: {len(tabela):,} | automóveis (4% referencial): {manifesto['total_automoveis_com_cenario_base']:,}")
    print(f"[OK] INMETRO candidatos textuais: {manifesto['total_candidatos_inmetro_com_correspondencia_textual']:,} | mestre {'encontrado' if mestre else 'não encontrado'}")
    print(f'[PUBLICADO] {destino.resolve()}')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raiz', type=Path, default=Path(__file__).resolve().parent, help='Raiz do projeto PI06')
    argumentos = parser.parse_args()
    executar(argumentos.raiz.resolve())

if __name__ == '__main__':
    main()
