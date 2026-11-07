"""PI06 — Etapa 1.8: padronização conservadora das fontes de veículos.

Uso: python padronizar_bases.py

Lê os CSVs existentes em dados_limpos, não altera originais, não faz merges.
Publica apenas tabelas cuja integridade estrutural e identidade foram validadas.
"""
from __future__ import annotations

import json
import hashlib
import shutil
import tempfile
import os
import re
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
ORIGEM = Path(os.getenv('PI_OUTPUT_DIR', ROOT / 'dados_limpos'))
DESTINO = ROOT / 'dados_padronizados'
RELATORIOS = Path(os.getenv('PI_REPORT_DIR', ROOT / 'dados_relatorios'))

FONTES_VEICULOS = {
    'inmetro': ('05_INMETRO_ORGANIZADO.csv', ('marca','modelo','versao','tipo_propulsao','consumo_energetico_mj_km','linha_origem_excel')),
    'fipe_parcial': ('08_FIPE_VEICULOS_PARCIAL.csv', ('brand_id','model_id','year_code','codigo_fipe','preco_fipe','mes_referencia')),
    'uber_modelos': ('09_UBER_MODELOS_SP.csv', ('marca','modelo')),
    'ocm': ('10_OPEN_CHARGE_MAP_SP.csv', ('id_posto','latitude','longitude','recorte_geografico')),
    'uber_match': ('17_UBER_MATCH_OFERTAS_SP.csv', ('id_publico_oferta','url_oferta','valor_reais','periodicidade_valor','status_qualidade','apto_modelo_economico')),
}


def normalizar(valor: object) -> str | None:
    if pd.isna(valor) or not str(valor).strip():
        return None
    n = unicodedata.normalize('NFKD',str(valor).strip().upper())
    n = n.encode('ascii','ignore').decode('ascii')
    n = re.sub(r'[^A-Z0-9]+',' ',n).strip()
    return re.sub(r'\s+',' ',n) or None


def monetario_fipe(valor: object) -> float | None:
    if pd.isna(valor) or not str(valor).strip():
        return None
    s=str(valor).strip()
    if not re.fullmatch(r'R\$\s*\d{1,3}(?:\.\d{3})*,\d{2}|R\$\s*\d+,\d{2}',s):
        raise ValueError(f'Valor monetário FIPE inválido: {s!r}')
    try:
        d=Decimal(s.replace('R$','').replace('.','').replace(',','.').strip())
    except InvalidOperation as exc:
        raise ValueError(f'Valor monetário FIPE inválido: {s!r}') from exc
    if d<=0:
        raise ValueError(f'Preço FIPE não positivo: {s!r}')
    return float(d)


def ler_csv(caminho: Path) -> pd.DataFrame:
    if not caminho.is_file():
        raise FileNotFoundError(f'Fonte obrigatória ausente: {caminho}')
    df=pd.read_csv(caminho,dtype='string',keep_default_na=False,encoding='utf-8-sig',low_memory=False)
    df.columns=[c.strip() for c in df.columns]
    if df.empty:
        raise ValueError(f'Fonte vazia: {caminho.name}')
    if df.columns.duplicated().any():
        raise ValueError(f'Colunas duplicadas: {caminho.name}')
    return df


def checar_chave(df: pd.DataFrame, campos: tuple[str,...], fonte: str) -> None:
    for c in campos:
        if df[c].isna().any() or df[c].str.strip().eq('').any():
            raise ValueError(f'{fonte}: chave com ausências: {c}')
    duplicadas=int(df.duplicated(list(campos)).sum())
    if duplicadas:
        raise ValueError(f'{fonte}: {duplicadas} chaves repetidas: {campos}')


def tratar(nome: str, df: pd.DataFrame) -> tuple[pd.DataFrame,list[str]]:
    x=df.copy()
    avisos=[]
    if nome=='inmetro':
        x['marca_chave']=x['marca'].map(normalizar).astype('string')
        x['modelo_chave']=x['modelo'].map(normalizar).astype('string')
        x['versao_chave']=x['versao'].map(normalizar).astype('string')
        x['tipo_propulsao_chave']=x['tipo_propulsao'].map(normalizar).astype('string')
        x['consumo_energetico_mj_km_num']=pd.to_numeric(x['consumo_energetico_mj_km'].str.replace(',','.',regex=False),errors='coerce')
        if (x['consumo_energetico_mj_km_num'].dropna()<=0).any():
            raise ValueError('INMETRO: consumo energético não positivo')
        checar_chave(x,('linha_origem_excel',),'INMETRO')
        avisos.append('Consumo MJ/km permanece com ausências; outras métricas km/l ou km/le não foram convertidas.')
    elif nome=='fipe_parcial':
        checar_chave(x,('brand_id','model_id','year_code','mes_referencia'),'FIPE')
        x['preco_fipe_brl']=x['preco_fipe'].map(monetario_fipe).astype('Float64')
        if x['preco_fipe_brl'].isna().any():
            raise ValueError('FIPE: preço ausente')
        x['marca_chave']=x['marca_fipe'].map(normalizar).astype('string')
        x['modelo_chave']=x['modelo_fipe'].map(normalizar).astype('string')
        if x['mes_referencia'].nunique()!=1:
            raise ValueError('FIPE: referências mensais distintas; não publicar juntas')
        avisos.append('Coleta FIPE PARCIAL; não juntar ao 08_FIPE_VEICULOS.csv antigo e não generalizar preços.')
    elif nome=='uber_modelos':
        x['marca_chave']=x['marca'].map(normalizar).astype('string')
        x['modelo_chave']=x['modelo'].map(normalizar).astype('string')
        for col in ['uberx_ano_min','comfort_ano_min','black_ano_min','electric_ano_min']:
            if col in x:
                numerico=pd.to_numeric(x[col],errors='coerce')
                if numerico.dropna().between(1900,2100).eq(False).any():
                    raise ValueError(f'Uber: ano inválido em {col}')
        avisos.append('Marca/modelo normalizados não provam elegibilidade por versão ou ano.')
    elif nome=='ocm':
        checar_chave(x,('id_posto',),'OCM')
        x['latitude_num']=pd.to_numeric(x['latitude'].str.replace(',','.',regex=False),errors='coerce')
        x['longitude_num']=pd.to_numeric(x['longitude'].str.replace(',','.',regex=False),errors='coerce')
        if x['latitude_num'].isna().any() or x['longitude_num'].isna().any():
            raise ValueError('OCM: coordenadas ausentes/inválidas')
        if not x['latitude_num'].between(-90,90).all() or not x['longitude_num'].between(-180,180).all():
            raise ValueError('OCM: coordenadas fora do intervalo')
        if not x['recorte_geografico'].eq('municipio_sao_paulo_ibge_3550308').all():
            raise ValueError('OCM: recorte diferente do município São Paulo')
        avisos.append('Coordenadas validadas numericamente; interseção espacial depende da etapa geográfica.')
    elif nome=='uber_match':
        checar_chave(x,('id_publico_oferta',),'Uber Match')
        x['veiculo_chave']=x['veiculo'].map(normalizar).astype('string') if 'veiculo' in x else pd.Series(pd.NA,index=x.index,dtype='string')
        x['valor_reais_num']=pd.to_numeric(x['valor_reais'].str.replace(',','.',regex=False),errors='coerce')
        if (x['valor_reais_num'].dropna()<=0).any():
            raise ValueError('Uber Match: preço não positivo')
        if not x['status_qualidade'].isin(['ok','revisar']).all():
            raise ValueError('Uber Match: status de qualidade inesperado')
        x['apto_modelo_economico_bool']=x['apto_modelo_economico'].str.casefold().map({'true':True,'false':False}).astype('boolean')
        if x['apto_modelo_economico_bool'].isna().any():
            raise ValueError('Uber Match: aptidão inválida')
        if ((x['status_qualidade']!='ok')&x['apto_modelo_economico_bool']).any():
            raise ValueError('Uber Match: oferta em revisão marcada apta')
        avisos.append('Oito links da categoria locação com opção de compra foram ignorados na indexação; cobertura incompleta.')
        avisos.append('Campos booleanos de inclusões devem ser interpretados conforme regras de extração, não como ausência comprovada.')
    return x,avisos



# Famílias adicionais, preservando a granularidade individual de cada fonte.
# A lista é intencional: não inclui a FIPE legada, INMETRO preliminar,
# falhas do Uber Match ou cópias auxiliares que poderiam contaminar análises.
FONTES_COMPLEMENTARES = {
    'aneel_nacional': ('02_ANEEL_NACIONAL.csv', 'tarifa por distribuidora/vigência/modalidade/posto', 'nacional (não inferir SP)', 'conforme Início Vigência / Fim Vigência'),
    'anp_sp': ('03_ANP_SP.csv', 'pesquisa de preço por revenda/produto/data', 'estado de São Paulo (verificar município)', 'datas em Data da Coleta'),
    'ibge_rmsp': ('04_IBGE_RMSP.csv', 'município', '39 municípios RMSP', 'cadastro municipal da fonte'),
    'ibge_sp': ('04_IBGE_SP.csv', 'município', 'estado de São Paulo', 'cadastro municipal da fonte'),
    'senatran_ano': ('06_SENATRAN_ANO_SP.csv', 'município × ano de veículo × demais dimensões da fonte', 'estado SP', 'julho de 2026; conferir origem'),
    'senatran_cep': ('06_SENATRAN_CEP_SP.csv', 'município × CEP × demais dimensões da fonte', 'estado SP', 'julho de 2026; conferir origem'),
    'senatran_combustivel': ('06_SENATRAN_COMBUSTIVEL_SP.csv', 'município × combustível × demais dimensões da fonte', 'estado SP', 'julho de 2026; conferir origem'),
    'senatran_marca_modelo': ('06_SENATRAN_MARCA_MODELO_SP.csv', 'município × marca/modelo × demais dimensões da fonte', 'estado SP', 'julho de 2026; conferir origem'),
    'senatran_potencia': ('06_SENATRAN_POTENCIA_SP.csv', 'município × potência × demais dimensões da fonte', 'estado SP', 'julho de 2026; conferir origem'),
    'senatran_tipo': ('06_SENATRAN_TIPO_VEICULO_SP.csv', 'município × tipo de veículo, colunas originalmente largas', 'estado SP', 'julho de 2026; conferir origem'),
    'od2023_app': ('07_ORIGEM_DESTINO.csv', 'viagem amostral OD; FE_VIA é fator de expansão', 'RMSP', 'Pesquisa OD 2023'),
    'abve_vendas_rmsp': ('11_ABVE_VENDAS_RMSP.csv', 'município × recorte de vendas da fonte', 'RMSP', 'referência não explícita no CSV'),
    'abve_vendas_capital': ('11_ABVE_VENDAS_SAO_PAULO.csv', 'município × recorte de vendas da fonte', 'município de São Paulo', 'referência não explícita no CSV'),
    'abve_modelos': ('14_ABVE_VENDAS_POR_MODELO.csv', 'ano × mês × fabricante × modelo', 'abrangência não declarada no CSV', 'colunas Ano e Mês'),
    'abve_eletropostos_rmsp': ('15_ABVE_ELETROPOSTOS_RMSP.csv', 'município × tipo AC/DC', 'RMSP', 'referência não explícita no CSV'),
    'abve_mhev_brasil': ('16_ABVE_VENDAS_MHEV_BRASIL.csv', 'município', 'Brasil', 'referência não explícita no CSV'),
    'abve_mhev_rmsp': ('16_ABVE_VENDAS_MHEV_RMSP.csv', 'município', 'RMSP', 'referência não explícita no CSV'),
    'abve_mhev_capital': ('16_ABVE_VENDAS_MHEV_SAO_PAULO.csv', 'município', 'município de São Paulo', 'referência não explícita no CSV'),
    'abve_evolucao_eletropostos_sp': ('17_ABVE_EVOLUCAO_ELETROPOSTOS_SP.csv', 'ano × mês', 'estado SP', 'colunas Ano e Mês'),
    'abve_resumo_tecnologia': ('abve_resumo_tecnologia.csv', 'ano × mês × tecnologia', 'abrangência não declarada no CSV', 'colunas Ano e Mês'),
}

# Bases deliberadamente não publicadas, para evitar arquivos conflitantes.
EXCLUIDOS = {
    '02_ANEEL_SP.csv': 'saída anterior com escopo estadual não demonstrado pela fonte atual',
    '05_INMETRO.csv': 'versão preliminar; utilizar 05_INMETRO_ORGANIZADO.csv',
    '05_INMETRO_BRUTO_VALIDACAO.csv': 'base intermediária de conferência, não versão analítica',
    '08_FIPE_VEICULOS.csv': 'FIPE legada; 1 registro na última auditoria, não misturar com coleta parcial',
    '17_UBER_MATCH_FALHAS_SP.csv': 'registro de avisos, não uma tabela de ofertas',
    'abve_vendas_modelos.csv': 'tabela potencialmente equivalente a 14_ABVE_VENDAS_POR_MODELO.csv; manter para conferência, não duplicar',
}

MARCADOR_AUSENCIA = {'', 'ND', 'N/D', 'N.A.', 'NA', 'N A', '-', '—', '–', '\\', 'NULL', 'NULO', 'NÃO INFORMADO', 'NAO INFORMADO', 'NAN'}
MAPA_MESES = {
    'JANEIRO': 1, 'FEVEREIRO': 2, 'MARCO': 3, 'ABRIL': 4,
    'MAIO': 5, 'JUNHO': 6, 'JULHO': 7, 'AGOSTO': 8,
    'SETEMBRO': 9, 'OUTUBRO': 10, 'NOVEMBRO': 11, 'DEZEMBRO': 12,
}


def _limpar_nome(nome: object) -> str:
    """Normaliza apenas para reconhecimento de colunas; não renomeia originais."""
    return normalizar(str(nome)) or ''


def _coluna(df: pd.DataFrame, *candidatas: str) -> str | None:
    chaves = {_limpar_nome(k): k for k in df.columns}
    for nome in candidatas:
        achada = chaves.get(_limpar_nome(nome))
        if achada is not None:
            return achada
    return None


def _ausente(series: pd.Series) -> pd.Series:
    x = series.astype('string').fillna('').str.strip()
    return x.map(lambda v: _limpar_nome(v) in MARCADOR_AUSENCIA or str(v).strip() in MARCADOR_AUSENCIA)


def _numero_br(texto: object) -> float | None:
    """Converte número explícito, sem imputar ausências e sem aceitar ambiguidade."""
    if pd.isna(texto):
        return None
    raw = str(texto).strip().replace('\xa0', '')
    if _limpar_nome(raw) in MARCADOR_AUSENCIA or raw in MARCADOR_AUSENCIA:
        return None
    raw = raw.replace(' ', '')
    if not re.fullmatch(r'[+-]?[0-9.,]+', raw):
        raise ValueError(f'Número não interpretável: {texto!r}')
    if ',' in raw and '.' in raw:
        if raw.rfind(',') > raw.rfind('.'):
            raw = raw.replace('.', '').replace(',', '.')
        else:
            raw = raw.replace(',', '')
    elif ',' in raw:
        raw = raw.replace('.', '').replace(',', '.')
    elif raw.count('.') > 1:
        raw = raw.replace('.', '')
    return float(Decimal(raw))


def _num_series(df: pd.DataFrame, original: str, nova: str, *, estrito: bool = True) -> int:
    """Retorna número de células numéricas inválidas; preserva originais."""
    valores = []
    invalidos = 0
    for v in df[original]:
        try:
            valores.append(_numero_br(v))
        except (ValueError, InvalidOperation):
            valores.append(None)
            invalidos += 1
    df[nova] = pd.Series(valores, index=df.index, dtype='Float64')
    if estrito and invalidos:
        raise ValueError(f'{original}: {invalidos} valores numéricos inválidos')
    return invalidos


def _mes_numero(v: object) -> int | None:
    if pd.isna(v) or not str(v).strip():
        return None
    val = _limpar_nome(v)
    if val.isdigit():
        n = int(val)
        return n if 1 <= n <= 12 else None
    return MAPA_MESES.get(val)


def _criar_municipio(df: pd.DataFrame, observacoes: list[str]) -> None:
    col = _coluna(df, 'Municipio', 'Município', 'NM_MUN')
    if col:
        df['municipio_chave'] = df[col].map(normalizar).astype('string')
        observacoes.append(f'municipio_chave: normalizado de {col}; não comprova identidade sem código IBGE')
    codigo = _coluna(df, 'CD_MUN')
    if codigo:
        cod = df[codigo].astype('string').str.strip()
        if cod.isna().any() or (~cod.str.fullmatch(r'\d{7}', na=False)).any():
            raise ValueError('IBGE: CD_MUN contém códigos inválidos (esperados 7 dígitos)')
        if cod.duplicated().any():
            raise ValueError('IBGE: CD_MUN duplicado')
        df['codigo_ibge_municipio'] = cod


def _validar_periodo(df: pd.DataFrame, notas: list[str]) -> None:
    col_ano = _coluna(df, 'Ano')
    col_mes = _coluna(df, 'Mês', 'Mes')
    if col_ano:
        _num_series(df, col_ano, 'ano_num')
        valores = df['ano_num'].dropna()
        if not valores.empty and (~valores.between(2000, 2100) | (valores % 1 != 0)).any():
            raise ValueError(f'Ano fora do intervalo em {col_ano}')
    if col_mes:
        mes = df[col_mes].map(_mes_numero)
        original = ~_ausente(df[col_mes])
        if mes[original].isna().any():
            raise ValueError(f'Mês inválido em {col_mes}')
        df['mes_num'] = pd.Series(mes, index=df.index, dtype='Int64')
    if col_ano and col_mes:
        df['referencia_ano_mes'] = (
            df['ano_num'].astype('Int64').astype('string')
            + '-' + df['mes_num'].astype('string').str.zfill(2)
        )
        notas.append('referencia_ano_mes derivada das colunas Ano e Mês (não da data de coleta)')


def tratar_complementar(nome: str, df: pd.DataFrame) -> tuple[pd.DataFrame, list[str], list[str]]:
    """Adiciona colunas comprováveis sem mudar granularidade e valores da fonte."""
    x = df.copy()
    notas = []
    alertas = []
    _criar_municipio(x, notas)
    _validar_periodo(x, notas)

    if nome.startswith('ibge_'):
        if 'codigo_ibge_municipio' not in x:
            raise ValueError('IBGE: código municipal CD_MUN não encontrado')
        if nome == 'ibge_rmsp' and len(x) != 39:
            alertas.append(f'RMSP: {len(x)} municípios, referência histórica esperada 39; conferir fonte')

    elif nome == 'anp_sp':
        col_valor = _coluna(x, 'Valor de Venda', 'Valor Venda')
        col_produto = _coluna(x, 'Produto')
        if not col_valor or not col_produto:
            raise ValueError('ANP: colunas Produto/Valor de Venda ausentes; não converter com base em suposição')
        _num_series(x, col_valor, 'preco_venda_brl_por_unidade_num')
        if (x['preco_venda_brl_por_unidade_num'].dropna() <= 0).any():
            raise ValueError('ANP: preço de venda não positivo')
        x['produto_chave'] = x[col_produto].map(normalizar).astype('string')
        col_data = _coluna(x, 'Data da Coleta')
        if col_data:
            dt = pd.to_datetime(x[col_data].replace('', pd.NA), errors='coerce', dayfirst=True)
            if (dt.isna() & ~_ausente(x[col_data])).any():
                raise ValueError('ANP: Data da Coleta inválida')
            x['data_pesquisa_iso'] = dt.dt.strftime('%Y-%m-%d').astype('string')
        notas.append('Preço por unidade da coluna original Unidade de Medida; não assumir sempre litro')

    elif nome == 'aneel_nacional':
        # O arquivo oficial atual pode utilizar nomes diferentes dos CSVs
        # antigos (por exemplo, VlrTE/VlrTUSD). A identificacao e explicita:
        # nunca renomear uma tarifa generica como TE ou TUSD por suposicao.
        aliases = {
            'te_num': ('TE', 'VlrTE', 'Valor TE', 'ValorTE', 'Tarifa Energia',
                       'Tarifa de Energia', 'VlrTarifaEnergia'),
            'tusd_num': ('TUSD', 'VlrTUSD', 'Valor TUSD', 'ValorTUSD',
                         'Tarifa Uso Sistema Distribuicao', 'VlrTarifaTUSD'),
        }
        localizadas = {}
        for campo, alternativas in aliases.items():
            original = _coluna(x, *alternativas)
            if original:
                _num_series(x, original, campo)
                localizadas[campo] = original
                notas.append(f'ANEEL: {campo} extraido explicitamente de {original}')

        col_unid = _coluna(x, 'Unidade', 'DscUnidade', 'DscUnidadeTarifaria',
                           'Unidade Medida', 'DscUnidadeMedida')
        if len(localizadas) != 2:
            faltantes = sorted(set(aliases) - set(localizadas))
            alertas.append(
                'ANEEL: padronizacao estrutural aprovada, MAS metricas '
                f'{faltantes} nao identificadas no esquema deste CSV. '
                'Nenhum valor foi inventado; verificar o dicionario oficial '
                f'antes do modelo economico. Colunas de entrada: {list(df.columns)}'
            )
        if col_unid:
            notas.append(
                f'ANEEL: unidade preservada em {col_unid}; tarifas nao podem '
                'ser somadas ou comparadas entre modalidades/postos sem filtro.'
            )
        else:
            alertas.append(
                'ANEEL: coluna de unidade tarifaria nao identificada; '
                'nao calcular custo em R$/kWh antes de identificar a unidade.'
            )
        notas.append(
            'ANEEL: base nacional. Nao inferir tarifa SP ou vigencia atual '
            'sem identificar distribuidora, modalidade, posto e datas.'
        )

    elif nome.startswith('senatran_'):
        col_qtd = _coluna(x, 'Qtd. Veículos', 'Quantidade de Veículos')
        if col_qtd:
            _num_series(x, col_qtd, 'qtd_veiculos_num')
            if (x['qtd_veiculos_num'].dropna() < 0).any():
                raise ValueError('SENATRAN: quantidade negativa')
        if nome == 'senatran_tipo':
            col_total = _coluna(x, 'TOTAL')
            if col_total:
                _num_series(x, col_total, 'total_veiculos_num')
        if nome == 'senatran_combustivel':
            col_comb = _coluna(x, 'Combustível Veículo')
            if col_comb:
                x['combustivel_chave'] = x[col_comb].map(normalizar).astype('string')
            original = _coluna(x, 'combustivel_original')
            categoria = _coluna(x, 'categoria_visualizacao')
            if original and categoria:
                diverg = x[original].astype('string').str.upper().eq('ALCOOL') & x[categoria].astype('string').str.upper().eq('GASOLINA')
                if diverg.any():
                    alertas.append(f'{int(diverg.sum())} linhas SENATRAN: ALCOOL classificado Gasolina; revisar regra anterior, NÃO usar categoria_visualizacao como combustível original')
        notas.append('SENATRAN: dimensões por arquivo distintas; não concatenar grupos de frota')

    elif nome == 'od2023_app':
        mod = _coluna(x, 'MODOPRIN')
        peso = _coluna(x, 'FE_VIA')
        if not mod or not peso:
            raise ValueError('OD: MODOPRIN ou FE_VIA ausentes')
        _num_series(x, mod, 'modoprin_num')
        if not x['modoprin_num'].eq(12).all():
            raise ValueError('OD: há registros não pertencentes ao modo aplicativo MODOPRIN=12')
        _num_series(x, peso, 'fator_expansao_num')
        if (x['fator_expansao_num'].dropna() < 0).any():
            raise ValueError('OD: fator de expansão negativo')
        for original, novo in [('DURACAO','duracao_original_num'),('DISTANCIA','distancia_original_num')]:
            col = _coluna(x, original)
            if col:
                _num_series(x, col, novo, estrito=False)
        notas.append('DISTANCIA da OD é linha reta, não distância percorrida na malha viária; verificar unidade no dicionário da OD')
        notas.append('Viagens agregadas devem ser ponderadas por FE_VIA, jamais usar contagem simples como total expandido')

    elif nome.startswith('abve_'):
        col_mun = _coluna(x, 'Municipio')
        if nome.endswith('capital') and col_mun:
            if not x['municipio_chave'].eq('SAO PAULO').all():
                raise ValueError('ABVE: arquivo da capital contém outros municípios')
        for original, novo in [
            ('Quantidade','quantidade_num'), ('Quantidade_MHEV','quantidade_mhev_num'),
            ('Total_Eletropostos','total_eletropostos_num'),
            ('Carregadores_AC','carregadores_ac_num'),('Carregadores_DC','carregadores_dc_num'),
            ('MarketShare','market_share_original_num'),
            ('MarketShare_Pct','market_share_pct_num'),
            ('MarketShare_MHEV_Pct','market_share_mhev_pct_num'),
            ('Participacao_Estadual_Pct','participacao_estadual_pct_num'),
            ('Quantidade_ou_Share','quantidade_ou_share_original_num'),
        ]:
            col = _coluna(x, original)
            if col:
                _num_series(x, col, novo)
        if 'market_share_original_num' in x:
            notas.append('MarketShare original: escala/denominador da fonte a confirmar antes de transformar em percentual')
        if 'quantidade_ou_share_original_num' in x:
            notas.append('Quantidade_ou_Share é variável mista, não presumir contagem absoluta')
        col_evol = _coluna(x, 'Evolucao_Percentual')
        if col_evol:
            vals = x[col_evol].astype('string').str.strip().str.replace('%','',regex=False)
            invalidos = _num_series(x.assign(_evol_num_original=vals), '_evol_num_original', 'evolucao_percentual_num', estrito=False)
            # Não redefinir evolução original caso haja um formato inesperado.
            x['evolucao_percentual_num'] = pd.Series([_numero_br(v) if v.strip() and re.fullmatch(r'[0-9.,+-]+',v.strip()) else None for v in vals], index=x.index,dtype='Float64')
            if invalidos:
                alertas.append(f'{invalidos} valores de evolução não interpretáveis')
        if nome == 'abve_eletropostos_rmsp' and {'total_eletropostos_num','carregadores_ac_num','carregadores_dc_num'} <= set(x.columns):
            diverg = (x['carregadores_ac_num'].fillna(0) + x['carregadores_dc_num'].fillna(0) - x['total_eletropostos_num']).abs()
            if (diverg > 0).any():
                alertas.append(f'{int((diverg>0).sum())} linhas: AC+DC diferente do total de eletropostos; checar definições das medidas')
    return x, notas, alertas


def _hash_arquivo(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open('rb') as f:
        for b in iter(lambda: f.read(1<<20), b''):
            h.update(b)
    return h.hexdigest()


def _dicionario(nome: str, arquivo: str, origem: pd.DataFrame, tratado: pd.DataFrame, granularidade: str, escopo: str, referencia: str) -> list[dict]:
    resultado = []
    for col in tratado.columns:
        tipo = str(tratado[col].dtype)
        original = col in origem.columns
        nulos = int(tratado[col].isna().sum())
        vazios = int(_ausente(tratado[col]).sum()) if original else nulos
        unidade = ''
        if col.endswith('_mj_km_num'): unidade='MJ/km'
        elif col.endswith('_km_l'): unidade='km/L'
        elif col in {'preco_fipe_brl','valor_reais_num','preco_venda_brl_por_unidade_num'}: unidade='BRL (por unidade informada pela fonte quando aplicável)'
        elif col.endswith('pct_num') or col == 'evolucao_percentual_num': unidade='% original informado'
        elif 'latitude' in col or 'longitude' in col: unidade='graus decimais'
        elif col.endswith('_km'): unidade='km (verificar definição)'
        elif col in {'quantidade_num','quantidade_mhev_num','qtd_veiculos_num'}: unidade='contagem'
        resultado.append({'fonte':nome,'arquivo':arquivo,'coluna':col,'origem_ou_derivada':'original' if original else 'derivada','tipo_saida':tipo,'ausencias_ou_marcadores':vazios,'unidade_indicativa':unidade,'granularidade':granularidade,'abrangencia':escopo,'referencia':referencia})
    return resultado


def executar() -> None:
    """Valida tudo primeiro; só publica depois de todas as fontes aprovadas."""
    RELATORIOS.mkdir(parents=True,exist_ok=True)
    DESTINO.mkdir(parents=True,exist_ok=True)
    resultado = []
    dicionario = []
    notas = []
    alertas = []
    erros = []
    fontes = dict(FONTES_VEICULOS)
    fontes.update({k:(v[0],()) for k,v in FONTES_COMPLEMENTARES.items()})
    with tempfile.TemporaryDirectory(prefix='pi06_etapa18_') as temp:
        estagio = Path(temp)
        for nome,(arquivo,colunas) in fontes.items():
            try:
                caminho=ORIGEM/arquivo
                df=ler_csv(caminho)
                faltantes=[c for c in colunas if c not in df.columns]
                if faltantes:
                    raise ValueError(f'Colunas obrigatórias ausentes: {faltantes}')
                if nome in FONTES_VEICULOS:
                    pad,avisos=tratar(nome,df)
                    granu='veículo/versão ou oferta/ponto, conforme fonte'
                    escopo='conforme extração e recorte'
                    ref='conforme CSV de origem'
                    notas.extend(f'{nome}: {v}' for v in avisos)
                else:
                    granu,escopo,ref=FONTES_COMPLEMENTARES[nome][1:]
                    pad,avisos,warnings=tratar_complementar(nome,df)
                    notas.extend(f'{nome}: {v}' for v in avisos)
                    alertas.extend(f'{nome}: {v}' for v in warnings)
                if len(pad)!=len(df):
                    raise ValueError(f'Quantidade de linhas alterada: {len(df)} -> {len(pad)}')
                if any(c not in pad.columns for c in df.columns):
                    raise ValueError('Alguma coluna original desapareceu')
                filename=estagio/arquivo
                pad.to_csv(filename,index=False,encoding='utf-8-sig')
                # Prova escrita e leitura com a mesma quantidade de linhas.
                with filename.open('r',encoding='utf-8-sig',newline='') as f:
                    linhas_arquivo = sum(1 for _ in f)-1
                if linhas_arquivo != len(pad):
                    # CSV pode conter quebra de linha em campos descritivos.
                    with filename.open('r',encoding='utf-8-sig',newline='') as f:
                        import csv
                        linhas_arquivo=sum(1 for _ in csv.reader(f))-1
                    if linhas_arquivo != len(pad):
                        raise ValueError('Contagem após escrita divergiu')
                dicionario.extend(_dicionario(nome,arquivo,df,pad,granu,escopo,ref))
                resultado.append({'fonte':nome,'arquivo':arquivo,'status':'aprovado','linhas':len(df),'colunas_origem':len(df.columns),'colunas_saida':len(pad.columns),'hash_sha256_origem':_hash_arquivo(caminho),'duplicatas_linha_original':int(df.duplicated().sum()),'observacoes':''})
                print(f'[OK] {nome}: {len(df)} linhas | {len(pad.columns)} colunas')
            except Exception as e:
                erros.append(f'{nome} ({arquivo}): {e}')
                resultado.append({'fonte':nome,'arquivo':arquivo,'status':'reprovado','linhas':'','colunas_origem':'','colunas_saida':'','hash_sha256_origem':'','duplicatas_linha_original':'','observacoes':str(e)})
                print(f'[ERRO] {nome}: {e}')

        pd.DataFrame(resultado).to_csv(RELATORIOS/'etapa18_validacao_padronizacao.csv',index=False,encoding='utf-8-sig')
        pd.DataFrame(dicionario).to_csv(RELATORIOS/'etapa18_dicionario_dados.csv',index=False,encoding='utf-8-sig')
        linhas=['# PI06 — Etapa 1.8: encerramento técnico',f'Execução UTC: {datetime.now(timezone.utc).isoformat()}','',f'Fontes selecionadas: {len(fontes)}. Aprovadas: {len(fontes)-len(erros)}. Reprovadas: {len(erros)}.','','## Política','- CSVs de dados_limpos preservados; padronização somente por colunas adicionais.','- Nenhum merge ou imputação de ND/traço/brancos.','- Arquivos de referência selecionados conscientemente por fonte/granularidade.','- Referências e coberturas distintas não podem ser confundidas.','','## Arquivos antigos/intermediários fora da publicação']
        linhas += [f'- `{p}`: {why}' for p,why in EXCLUIDOS.items()]
        linhas += ['', '## Limitações e próximos passos', '- FIPE parcial: 489 cotações na referência de novembro de 2026; a cobertura está incompleta.', '- Uber Match: oito links foram ignorados por categoria classificada Serviços; revisão pendente.', '- ANEEL: nacional, não se deve atribuir tarifa municipal por inferência.', '- ABVE: conferir denominadores e abrangência de MarketShare.', '- SENATRAN: não confundir categoria_visualizacao com combustível original sem revisão.', '- OD: fator de expansão FE_VIA, granularidade viagem; distância em linha reta.', '- Não executar merges até validação de cardinalidade, referência, chaves e identidade.', '', '## Notas das transformações']
        linhas += [f'- {x}' for x in notas]
        if alertas: linhas+=['','## Alertas não bloqueantes'] + [f'- {x}' for x in alertas]
        if erros: linhas+=['','## Erros bloqueantes'] + [f'- {x}' for x in erros]
        linhas+=['','## Publicação', ('BLOQUEADA: dados_padronizados anterior preservado' if erros else ('APROVADA ESTRUTURALMENTE COM ALERTAS: revisar as pendencias antes dos calculos economicos' if alertas else 'APROVADA'))]
        (RELATORIOS/'etapa18_padronizacao.md').write_text('\n'.join(linhas)+'\n',encoding='utf-8')
        if erros:
            raise RuntimeError(f'{len(erros)} fonte(s) reprovadas. Nenhuma nova tabela publicada; consulte dados_relatorios/etapa18_padronizacao.md')
        # Primeiro verifica a quantidade de originais e a lista gerada; não apaga saídas antigas.
        publicados=[]
        for nome,(arquivo,_) in fontes.items():
            alvo=DESTINO/arquivo
            origem_pad=estagio/arquivo
            tmp=alvo.with_suffix('.csv.tmp')
            shutil.copyfile(origem_pad,tmp)
            os.replace(tmp,alvo)
            publicados.append(arquivo)
            print(f'[PUBLICADO] {alvo}')
        (RELATORIOS/'etapa18_arquivos_publicados.json').write_text(json.dumps({'data_utc':datetime.now(timezone.utc).isoformat(),'arquivos':publicados,'excluidos':EXCLUIDOS},ensure_ascii=False,indent=2),encoding='utf-8')
        print(f'\nETAPA 1.8: {len(publicados)} tabelas selecionadas padronizadas; originais preservados; consulte relatório.')

if __name__=='__main__':
    executar()
