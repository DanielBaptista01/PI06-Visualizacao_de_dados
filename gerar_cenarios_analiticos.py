"""PI06 — camada analítica para mapa OD e simulador econômico (sem joins artificiais).

Execute na raiz do repositório: python gerar_cenarios_analiticos.py
Requer pandas; não altera dados de entrada nem carrega o Supabase.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

DIR_OD = Path('dados_relatorios/territorio_od2023')
DIR_ENERGIA = Path('dados_relatorios/consolidacao_integrada')
DIR_ECONOMIA = Path('dados_relatorios/economia_completa')
DIR_CONFIG = Path('dados_config')
DIR_SAIDA = Path('dados_analiticos/cenarios_2026')

CUSTOS = (
    'custo_energia_rs_mes', 'custo_manutencao_rs_mes', 'custo_pneus_rs_mes',
    'custo_seguro_rs_mes', 'custo_ipva_rs_mes', 'custo_licenciamento_rs_mes',
    'custo_lavagem_rs_mes', 'custo_celular_rs_mes', 'custo_outros_fixos_rs_mes',
    'custo_depreciacao_rs_mes', 'custo_aluguel_rs_mes',
)
FAIXAS = ('Madrugada (0-5)', 'Manhã (6-11)', 'Tarde (12-17)',
          'Noite (18-23)', 'Hora desconhecida')


def read_csv(path: Path, columns: tuple[str, ...] | list[str]) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f'Entrada ausente: {path}. Execute o pipeline correspondente antes.')
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding='utf-8-sig')
    missing = set(columns).difference(frame.columns)
    if missing:
        raise ValueError(f'{path}: colunas obrigatórias ausentes: {sorted(missing)}')
    if frame.empty:
        raise ValueError(f'{path}: tabela vazia')
    return frame


def number(series: pd.Series, *, allow_negative: bool = False) -> pd.Series:
    """Lê CSV decimal comum (ponto) ou pt-BR; vazio nunca vira zero."""
    strings = series.astype('string').fillna('').str.strip().str.replace('R$', '', regex=False)
    strings = strings.str.replace(' ', '', regex=False)
    both = strings.str.contains('.', regex=False) & strings.str.contains(',', regex=False)
    strings.loc[both] = strings.loc[both].str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
    comma_only = strings.str.contains(',', regex=False)
    strings.loc[comma_only] = strings.loc[comma_only].str.replace(',', '.', regex=False)
    numeric = pd.to_numeric(strings.replace('', pd.NA), errors='coerce')
    invalid = strings.ne('') & numeric.isna()
    if invalid.any():
        raise ValueError(f'Valores numéricos inválidos: {strings.loc[invalid].head(4).tolist()}')
    if (~numeric.dropna().map(lambda x: bool(pd.notna(x) and abs(x) != float('inf')))).any():
        raise ValueError('Número infinito não permitido')
    if not allow_negative and numeric.dropna().lt(0).any():
        raise ValueError('Valores negativos não permitidos neste campo')
    return numeric.astype('float64')


def unique(df: pd.DataFrame, cols: list[str], label: str) -> None:
    if df.duplicated(subset=cols).any():
        raise ValueError(f'{label}: chave duplicada {cols}')
    for c in cols:
        if df[c].astype(str).str.strip().eq('').any():
            raise ValueError(f'{label}: chave vazia {c}')


def grupo_tecnologia(v: object) -> str:
    name = str(v).casefold().replace('í', 'i').replace('é', 'e').strip()
    if 'hibrid' in name:
        return 'Híbrido'
    if 'eletric' in name:
        return 'Elétrico'
    if 'combust' in name:
        return 'Gasolina'  # grupo de navegação: inclui modalidade etanol/flex
    return 'Não classificado'


def territorial(zonas: pd.DataFrame, fluxos: pd.DataFrame, n_destinos: int,
                validar_baseline: bool = True) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    unique(zonas, ['zona_od_id'], 'Indicadores OD')
    for col in ['zona_od_id', 'municipio_od_id', 'distrito_od_id']:
        zonas[col] = number(zonas[col])
        if zonas[col].isna().any() or (zonas[col] % 1).ne(0).any():
            raise ValueError(f'ID territorial ausente ou fracionário: {col}')
        zonas[col] = zonas[col].astype(int)
    if validar_baseline:
        if (len(zonas), zonas['municipio_od_id'].nunique(),
                int(zonas['municipio_od_id'].eq(36).sum())) != (527, 39, 343):
            raise ValueError('Baseline OD divergiu de 527 zonas, 39 municípios, 343 zonas na capital')
    for col in ['viagens_origem_amostra','viagens_origem_expandidas',
                'viagens_destino_amostra','viagens_destino_expandidas']:
        zonas[col] = number(zonas[col])
    for lado in ['origem','destino']:
        flag = zonas[f'tem_amostra_{lado}'].str.lower().str.strip()
        if not flag.isin(('true','false')).all():
            raise ValueError(f'tem_amostra_{lado}: flag inválido')
        zonas[f'tem_amostra_{lado}'] = flag.eq('true')
        expected = zonas[f'viagens_{lado}_amostra'].notna()
        if not expected.eq(zonas[f'tem_amostra_{lado}']).all():
            raise ValueError(f'Inconsistência entre presença e contagem de amostra {lado}')
    zona_set = set(zonas['zona_od_id'])
    for c in ['zona_origem_id','zona_destino_id']:
        fluxos[c] = number(fluxos[c])
        if fluxos[c].isna().any() or (fluxos[c] % 1).ne(0).any():
            raise ValueError(f'Fluxos OD: {c} vazio ou fracionário')
        fluxos[c] = fluxos[c].astype(int)
        if not set(fluxos[c]).issubset(zona_set):
            raise ValueError(f'Fluxos OD: {c} contém zona fora do catálogo')
    unique(fluxos, ['zona_origem_id','zona_destino_id','faixa_horaria'], 'Fluxos OD')
    if not set(fluxos['faixa_horaria']).issubset(FAIXAS):
        raise ValueError('Fluxos OD: faixa horária desconhecida')
    fluxos['viagens_amostra'] = number(fluxos['viagens_amostra'])
    fluxos['viagens_expandidas'] = number(fluxos['viagens_expandidas'])
    if fluxos['viagens_expandidas'].isna().any() or fluxos['viagens_amostra'].isna().any():
        raise ValueError('Fluxo OD sem peso ou contagem')
    zone_cols = ['zona_od_id','zona_nome','municipio_od_id','municipio_nome',
                 'distrito_od_id','distrito_nome','escopo',
                 'viagens_origem_amostra','viagens_origem_expandidas',
                 'viagens_destino_amostra','viagens_destino_expandidas',
                 'tem_amostra_origem','tem_amostra_destino']
    painel = zonas[zone_cols].copy()
    painel['fonte'] = 'METRO_OD_2023_MODOPRIN_12'
    painel['natureza_dado'] = 'AMOSTRAL_EXPANDIDO'
    painel['observacao'] = ('Táxi não convencional/aplicativo; FE_VIA não é número de motoristas. '
                           'Ausência de amostra não é zero de demanda.')
    top = fluxos.sort_values(
        ['zona_origem_id','faixa_horaria','viagens_expandidas','zona_destino_id'],
        ascending=[True,True,False,True],kind='stable').copy()
    top['posicao'] = top.groupby(['zona_origem_id','faixa_horaria']).cumcount() + 1
    top = top[top['posicao'] <= n_destinos].copy()
    top = top.merge(zonas[['zona_od_id','zona_nome','municipio_nome']].rename(columns={
        'zona_od_id':'zona_destino_id','zona_nome':'nome_zona_destino',
        'municipio_nome':'municipio_destino'}),on='zona_destino_id',how='left',validate='many_to_one')
    top['fonte'] = 'METRO_OD_2023_MODOPRIN_12'
    top['natureza_dado'] = 'AMOSTRAL_EXPANDIDO'
    top['observacao'] = 'DISTANCIA é linha reta, não percurso viário ou km do motorista'
    return painel, top, {
        'zonas':len(zonas),'municipios':int(zonas['municipio_od_id'].nunique()),
        'zonas_capital':int(zonas['municipio_od_id'].eq(36).sum()),
        'zonas_com_amostra_origem':int(painel['tem_amostra_origem'].sum()),
        'zonas_com_amostra_destino':int(painel['tem_amostra_destino'].sum()),
        'fluxos_originais':len(fluxos),'fluxos_top':len(top),
    }


def resumos_hierarquia(painel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Agregação territorial real: NULL quando todas as zonas do grupo não têm amostra."""
    def aggregate(grouping: list[str], data: pd.DataFrame) -> pd.DataFrame:
        frame = data.groupby(grouping, as_index=False, dropna=False).agg(
            qtd_zonas=('zona_od_id','size'),
            zonas_com_amostra_origem=('tem_amostra_origem','sum'),
            zonas_com_amostra_destino=('tem_amostra_destino','sum'),
            viagens_origem_amostra=('viagens_origem_amostra',lambda s:s.sum(min_count=1)),
            viagens_origem_expandidas=('viagens_origem_expandidas',lambda s:s.sum(min_count=1)),
            viagens_destino_amostra=('viagens_destino_amostra',lambda s:s.sum(min_count=1)),
            viagens_destino_expandidas=('viagens_destino_expandidas',lambda s:s.sum(min_count=1)),
        )
        frame['fonte']='METRO_OD_2023_MODOPRIN_12'
        frame['natureza_dado']='AMOSTRAL_EXPANDIDO'
        return frame
    municipios=aggregate(['municipio_od_id','municipio_nome'],painel)
    capital=painel.loc[painel['municipio_od_id'].eq(36)]
    distritos=aggregate(['distrito_od_id','distrito_nome'],capital)
    return municipios,distritos


def energia_tecnica(df: pd.DataFrame) -> pd.DataFrame:
    unique(df,['inmetro_id','modalidade'],'Energia INMETRO')
    out = df[['inmetro_id','marca_inmetro','modelo_inmetro','versao_inmetro',
              'tecnologia','modalidade','custo_energia_rs_km']].copy()
    out['custo_energia_rs_km'] = number(out['custo_energia_rs_km'])
    if out['custo_energia_rs_km'].isna().any():
        raise ValueError('Energia INMETRO sem custo por km')
    out['km_mes_hipotese'] = number(df['km_mes_hipotese'])
    if out['km_mes_hipotese'].isna().any() or out['km_mes_hipotese'].le(0).any():
        raise ValueError('Energia INMETRO: km mensal inválido')
    out['custo_energia_rs_mes_hipotetico'] = (out['km_mes_hipotese'] * out['custo_energia_rs_km']).round(2)
    out['grupo_interface'] = out['tecnologia'].map(grupo_tecnologia)
    out['fonte'] = 'INMETRO_PBEV+ANP_2026+ANEEL_2026'
    out['natureza_dado'] = 'SIMULADO_ENERGIA'
    out['observacao'] = ('Custo técnico independente de FIPE; energia residencial sem tributos. '
                         'Não constitui homologação FIPE-INMETRO ou elegibilidade Uber.')
    return out


def custos_motorista(df: pd.DataFrame) -> pd.DataFrame:
    unique(df,['perfil_id','inmetro_id','modalidade'],'Motorista')
    out = df[['perfil_id','regime','inmetro_id','marca_inmetro','modelo_inmetro',
              'versao_inmetro','tecnologia','modalidade','status','campos_pendentes',
              'fonte_premissas','km_mes','receita_liquida_plataforma_rs_mes',
              'custo_total_economico_rs_mes','resultado_economico_rs_mes',
              'custo_total_rs_km','receita_equilibrio_rs_km','receita_equilibrio_rs_hora']].copy()
    for col in ['km_mes','receita_liquida_plataforma_rs_mes','custo_total_economico_rs_mes',
                'custo_total_rs_km','receita_equilibrio_rs_km','receita_equilibrio_rs_hora']:
        out[col] = number(out[col])
    out['resultado_economico_rs_mes'] = number(out['resultado_economico_rs_mes'],allow_negative=True)
    if out['km_mes'].isna().any() or out['km_mes'].le(0).any():
        raise ValueError('Motorista: km_mes precisa ser positivo')
    if not out['status'].isin(['COMPLETO_CENARIO','PARCIAL_PENDENTE']).all():
        raise ValueError('Motorista: status desconhecido')
    cost_numeric = pd.DataFrame({col:number(df[col]) for col in CUSTOS})
    out['componentes_custos_informados'] = cost_numeric.notna().sum(axis=1)
    out['componentes_custos_pendentes'] = cost_numeric.isna().sum(axis=1)
    out['subtotal_custos_conhecidos_rs_mes'] = cost_numeric.sum(axis=1,min_count=1).round(2)
    out['todos_custos_preenchidos'] = out['componentes_custos_pendentes'].eq(0)
    if out['status'].eq('COMPLETO_CENARIO').any():
        complete=out['status'].eq('COMPLETO_CENARIO')
        if ((~out.loc[complete,'todos_custos_preenchidos']) |
            out.loc[complete,'custo_total_economico_rs_mes'].isna() |
            out.loc[complete,'receita_liquida_plataforma_rs_mes'].isna()).any():
            raise ValueError('Motorista: status completo com lacunas de custos ou receita')
    # Não deixar lucro preenchido em status parcial por dados inconsistentes.
    bad_profit=out['status'].eq('PARCIAL_PENDENTE') & out['resultado_economico_rs_mes'].notna()
    if bad_profit.any():
        raise ValueError('Motorista: resultado em cenário parcial; verificar código anterior')
    # Nem custo total nem subtotal podem ser usados para deduzir resultado completo se houver lacuna.
    out.loc[~out['todos_custos_preenchidos'],'custo_total_economico_rs_mes']=float('nan')
    out.loc[~out['todos_custos_preenchidos'],'custo_total_rs_km']=float('nan')
    out.loc[~out['todos_custos_preenchidos'],'receita_equilibrio_rs_km']=float('nan')
    out.loc[~out['todos_custos_preenchidos'],'receita_equilibrio_rs_hora']=float('nan')
    out.loc[~out['todos_custos_preenchidos'],'resultado_economico_rs_mes']=float('nan')
    out['grupo_interface']=out['tecnologia'].map(grupo_tecnologia)
    out['fonte'] = 'ECONOMIA_COMPLETA_PI06_INMETRO'
    out['natureza_dado'] = 'SIMULADO_COM_PREMISSAS' 
    out['observacao'] = ('Subtotal conhecido não é custo total. Resultado econômico depende de '
                          'todos os custos e da receita; não é lucro observado.')
    return out


def renda_premissas(df: pd.DataFrame) -> pd.DataFrame:
    unique(df,['cenario_receita_id'],'Premissas de receita')
    valid=df[['cenario_receita_id','titulo','receita_apos_plataforma_rs_mes','fonte','observacao']].copy()
    valid['receita_apos_plataforma_rs_mes']=number(valid['receita_apos_plataforma_rs_mes'])
    if valid['receita_apos_plataforma_rs_mes'].isna().any():
        raise ValueError('Premissa de receita: falta valor')
    if not valid['fonte'].eq('HIPOTESE_DIDATICA_NAO_OBSERVADA').all():
        raise ValueError('A receita de referência deste bloco deve ser rotulada como hipótese')
    valid['natureza_dado']='HIPOTESE_DIDATICA'
    return valid


def sensibilidade_receita(motorista: pd.DataFrame, renda: pd.DataFrame) -> pd.DataFrame:
    # Produto cartesiano apenas PERFIL INMETRO × HIPÓTESES DE RECEITA: nenhum território OD.
    left=motorista[['perfil_id','regime','inmetro_id','modalidade','tecnologia',
                    'grupo_interface','km_mes','custo_total_economico_rs_mes',
                    'subtotal_custos_conhecidos_rs_mes','componentes_custos_pendentes',
                    'campos_pendentes','todos_custos_preenchidos']].copy()
    v=left.merge(renda[['cenario_receita_id','receita_apos_plataforma_rs_mes']], how='cross')
    complete=v['todos_custos_preenchidos'] & v['custo_total_economico_rs_mes'].notna()
    v['resultado_economico_simulado_rs_mes']=(v['receita_apos_plataforma_rs_mes'] -
                                                v['custo_total_economico_rs_mes']).where(complete)
    v['resultado_simulado_rs_km']=(v['resultado_economico_simulado_rs_mes']/v['km_mes']).where(complete)
    v['situacao_calculo'] = 'CUSTOS_INCOMPLETOS_SEM_RESULTADO'
    v.loc[complete,'situacao_calculo']='RESULTADO_SOMENTE_COM_HIPOTESE_DE_RECEITA'
    v['natureza_dado']='SIMULACAO_HIPOTETICA'
    v['observacao']=('Receita escolhida didaticamente após taxa da plataforma, antes dos custos. '
                     'Não é remuneração medida; nunca atribuir à zona OD.')
    return v


def digest(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def executar(raiz: Path, od: Path, energia: Path, economia: Path,
             receita: Path, saida: Path, n_destinos: int = 5,
             validar_baseline: bool = True, sobrescrever: bool = False) -> dict:
    if n_destinos<1 or n_destinos>50:
        raise ValueError('top destinos deve estar de 1 a 50')
    inputs={
        'zonas':od/'indicadores_zonas_od2023.csv',
        'fluxos':od/'fato_od_fluxos_zona_faixa.csv',
        'energia':energia/'fato_cenarios_inmetro_energia.csv',
        'motorista':economia/'fato_cenarios_motorista.csv',
        'receita':receita,
    }
    # Validar todas as entradas antes de produzir qualquer saída.
    zones=read_csv(inputs['zonas'],['zona_od_id','zona_nome','municipio_od_id','municipio_nome',
        'distrito_od_id','distrito_nome','escopo','viagens_origem_amostra','viagens_origem_expandidas',
        'viagens_destino_amostra','viagens_destino_expandidas','tem_amostra_origem','tem_amostra_destino'])
    flows=read_csv(inputs['fluxos'],['zona_origem_id','zona_destino_id','faixa_horaria',
        'viagens_amostra','viagens_expandidas'])
    energy=read_csv(inputs['energia'],['inmetro_id','marca_inmetro','modelo_inmetro',
        'versao_inmetro','tecnologia','modalidade','custo_energia_rs_km','km_mes_hipotese'])
    econ=read_csv(inputs['motorista'],['perfil_id','regime','inmetro_id',
        'marca_inmetro','modelo_inmetro','versao_inmetro','tecnologia','modalidade',
        'status','campos_pendentes','fonte_premissas','km_mes',
        'receita_liquida_plataforma_rs_mes','custo_total_economico_rs_mes',
        'resultado_economico_rs_mes','custo_total_rs_km','receita_equilibrio_rs_km',
        'receita_equilibrio_rs_hora',*CUSTOS])
    earnings=read_csv(inputs['receita'],['cenario_receita_id','titulo',
        'receita_apos_plataforma_rs_mes','fonte','observacao'])
    painel_zonas, destinos, geo_report=territorial(zones,flows,n_destinos,validar_baseline)
    municipios_painel, distritos_painel=resumos_hierarquia(painel_zonas)
    if validar_baseline and (len(municipios_painel)!=39 or len(distritos_painel)!=96):
        raise ValueError('Dimensões territoriais não possuem 39 municípios e 96 distritos de São Paulo')
    geo_report['distritos_capital']=len(distritos_painel)
    energy_panel=energia_tecnica(energy)
    driver_panel=custos_motorista(econ)
    # Garantir que todas as linhas econômicas correspondam à mesma versão/modalidade INMETRO.
    keys=energy_panel[['inmetro_id','modalidade']]
    joined=driver_panel[['inmetro_id','modalidade']].merge(
        keys.assign(_ok=1),on=['inmetro_id','modalidade'],how='left',validate='many_to_one')
    if joined['_ok'].isna().any():
        raise ValueError('Motorista: existe cenário sem energia correspondente INMETRO')
    earning_premises=renda_premissas(earnings)
    sensitivity=sensibilidade_receita(driver_panel,earning_premises)
    output={
        'painel_od_zonas.csv':painel_zonas,
        'painel_od_municipios.csv':municipios_painel,
        'painel_od_distritos_capital.csv':distritos_painel,
        'painel_od_top_destinos.csv':destinos,
        'painel_energia_inmetro.csv':energy_panel,
        'painel_motorista_custos.csv':driver_panel,
        'dim_premissas_receita.csv':earning_premises,
        'painel_sensibilidade_receita.csv':sensitivity,
    }
    manifest_name='manifesto_cenarios_analiticos.json'
    if not sobrescrever and any((saida/name).exists() for name in [*output,manifest_name]):
        raise FileExistsError(f'Arquivos de saída já existem: {saida}. Use --sobrescrever para recalcular')
    saida.mkdir(parents=True,exist_ok=True)
    for file,frame in output.items():
        frame.to_csv(saida/file,index=False,encoding='utf-8-sig',na_rep='')
    report={
        'gerado_em_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'versao':'1.0',
        'resumo_od':geo_report,
        'energia_cenarios':len(energy_panel),
        'motorista_cenarios':len(driver_panel),
        'motorista_custos_completos':int(driver_panel['todos_custos_preenchidos'].sum()),
        'motorista_status_completo':int(driver_panel['status'].eq('COMPLETO_CENARIO').sum()),
        'receitas_hipoteticas':len(earning_premises),
        'sensibilidade_linhas':len(sensitivity),
        'sensibilidade_com_resultado':int(sensitivity['resultado_economico_simulado_rs_mes'].notna().sum()),
        'entradas_sha256':{key:{'caminho':str(path),'sha256':digest(path)} for key,path in inputs.items()},
        'saidas_sha256':{key:{'linhas':len(frame),'sha256':digest(saida/key)} for key,frame in output.items()},
        'regras_de_integridade':[
            'OD 2023 MODOPRIN=12 não é base exclusiva da Uber',
            'Viagens expandidas FE_VIA não são número de motoristas nem faturamento',
            'Cenários FIPE-INMETRO não homologados não recebem preço FIPE',
            'Receitas didáticas não são fatos observados',
            'Custo total e resultado são NULL quando custos não estão completos',
            'Não existe junção zona OD x lucro do motorista',
            'GeoJSON é produzido por integrar_od2023.py e não por este processo',
        ],
    }
    (saida/manifest_name).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raiz',type=Path,default=Path('.'))
    parser.add_argument('--od',type=Path,default=DIR_OD)
    parser.add_argument('--energia',type=Path,default=DIR_ENERGIA)
    parser.add_argument('--economia',type=Path,default=DIR_ECONOMIA)
    parser.add_argument('--receita',type=Path,default=DIR_CONFIG/'cenarios_receita_analitica.csv')
    parser.add_argument('--saida',type=Path,default=DIR_SAIDA)
    parser.add_argument('--top-destinos',type=int,default=5)
    parser.add_argument('--sem-validar-baseline',action='store_true',help='Somente testes/base OD não-padrão')
    parser.add_argument('--sobrescrever',action='store_true')
    args=parser.parse_args()
    root=args.raiz
    executar(root,root/args.od,root/args.energia,root/args.economia,
            root/args.receita,root/args.saida,args.top_destinos,
            not args.sem_validar_baseline,args.sobrescrever)
