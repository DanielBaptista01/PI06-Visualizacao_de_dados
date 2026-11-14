"""PI06 — consolidação única FIPE/INMETRO/UBER e simulações energéticas.
Lê dados_limpos; não altera originais, checkpoints ou scripts antigos.
Não homologa automaticamente versões/anos, nem presume receita/lucro.
"""
from __future__ import annotations
import argparse
import json
import re
import unicodedata
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import pandas as pd

BRANDS = {'GM CHEVROLET':'CHEVROLET','GM':'CHEVROLET','KIA MOTORS':'KIA',
          'VW VOLKSWAGEN':'VOLKSWAGEN','VW':'VOLKSWAGEN','JAC MOTORS':'JAC'}
CATS = {'UberX':'uberx_ano_min','Comfort':'comfort_ano_min',
        'Black':'black_ano_min','Electric':'electric_ano_min'}

def norm(v):
    if pd.isna(v): return ''
    s=''.join(ch for ch in unicodedata.normalize('NFKD',str(v).upper()) if not unicodedata.combining(ch))
    return ' '.join(re.sub(r'[^A-Z0-9]+',' ',s).split())

def brand(v):
    s=norm(v)
    return BRANDS.get(s,s)

def prefix_model(full, model):
    """Modelo do catálogo é prefixo completo da descrição FIPE, com limite de palavra."""
    return bool(model) and (full==model or full.startswith(model+' '))

def family_match(full, model):
    """Recusa famílias diferentes: DOLPHIN MINI!=DOLPHIN, ORA 03!=ORA 5.
    Uma descrição FIPE sem variante (ORA 03) não é automaticamente versão INMETRO.
    """
    if not prefix_model(full, model): return False
    # Se a ficha FIPE contém um sufixo que estende família, exigir checagem posterior.
    return True

def price_brl(s):
    s=str(s or '').replace('R$','').replace(' ','')
    if ',' in s and '.' in s: s=s.replace('.','').replace(',','.')
    elif ',' in s: s=s.replace(',','.')
    return pd.to_numeric(s,errors='coerce')

def num(s):
    if pd.isna(s): return None
    s=str(s).strip()
    if s.upper() in ('','ND','N.A.','NA','NAN','-'): return None
    s=s.replace(',','.')
    try:
        v=float(s)
        return v if v>0 else None
    except ValueError: return None

def tech(tipo):
    n=norm(tipo)
    if 'PLUG' in n: return 'Hibrido plug-in'
    if 'HIBR' in n: return 'Hibrido'
    if 'ELETR' in n: return 'Eletrico'
    if 'COMBUST' in n: return 'Combustao'
    return 'Indefinido'

def fuel_compat(f, t):
    f=norm(f)
    if 'ELETR' in f: return t=='Eletrico'
    if 'HIBR' in f: return t.startswith('Hibrido') # híbridos leves podem exigir revisão
    if any(x in f for x in ('FLEX','GASOLINA','ETANOL','ALCOOL','DIESEL')):
        return t=='Combustao' or t.startswith('Hibrido') # alerta: possível flex híbrido
    return False

def read_required(path, fields):
    if not path.is_file(): raise FileNotFoundError(f'Arquivo ausente: {path}')
    df=pd.read_csv(path,encoding='utf-8-sig',dtype=str,low_memory=False).fillna('')
    missing=set(fields)-set(df.columns)
    if missing: raise ValueError(f'{path.name} faltam colunas {sorted(missing)}')
    return df

def run(root, out, km, efficiency):
    base=root/'dados_limpos'
    fi=read_required(base/'08_FIPE_VEICULOS_PARCIAL.csv',
      ['brand_id','model_id','year_code','marca_fipe','modelo_fipe','ano_modelo','combustivel_fipe','preco_fipe','mes_referencia'])
    im=read_required(base/'05_INMETRO_VALIDADO.csv',
      ['marca','modelo','versao','tipo_propulsao','linha_origem_excel','consumo_energetico_mj_km','consumo_gasolina_diesel_cidade_km_l','consumo_etanol_cidade_km_l'])
    ub=read_required(base/'09_UBER_MODELOS_SP.csv',['marca','modelo',*CATS.values()])
    an=read_required(base/'03_ANP_PRECOS_CAPITAL_NOV2026.csv',['municipio','produto','preco_medio_rs_litro'])
    ae=read_required(base/'02_ANEEL_CENARIO_ENERGIA_SP.csv',['tarifa_com_bandeira_rs_kwh','inclui_tributos'])
    if km<=0 or not (0<efficiency<=1): raise ValueError('km deve ser positivo e eficiencia (0,1]')
    fi=fi.drop_duplicates(['brand_id','model_id','year_code'],keep='last').copy()
    refs=set(fi['mes_referencia'].str.strip())
    if refs!={'novembro de 2026'}: raise ValueError(f'Referência FIPE inesperada: {refs}')
    fi['veiculo_id']=fi[['brand_id','model_id','year_code']].agg(':'.join,axis=1)
    fi['marca_key']=fi['marca_fipe'].map(brand)
    fi['nome_key']=fi['modelo_fipe'].map(norm)
    fi['ano_num']=pd.to_numeric(fi['ano_modelo'],errors='coerce')
    fi['preco_fipe_rs']=fi['preco_fipe'].map(price_brl)
    im['marca_key']=im['marca'].map(brand)
    im['modelo_key']=im['modelo'].map(norm)
    im['tecnologia']=im['tipo_propulsao'].map(tech)
    ub['marca_key']=ub['marca'].map(brand)
    ub['modelo_key']=ub['modelo'].map(norm)
    # Duplicatas no INMETRO sem alterar identidade de origem
    im['inmetro_id']=im['linha_origem_excel'].astype(str)
    if im['inmetro_id'].duplicated().any():
        im['inmetro_id']=im.index.map(lambda x:f'index:{x}')
    ig={k:g for k,g in im.groupby('marca_key')}
    ug={k:g for k,g in ub.groupby('marca_key')}
    links=[]; uber_rows=[]; summaries=[]
    for v in fi.itertuples(index=False):
        vehicle=v.veiculo_id; name=v.nome_key
        # longest *valid* family: DOLPHIN MINI takes precedence over DOLPHIN
        grp=ig.get(v.marca_key)
        candidates=[]
        if grp is not None:
            valid=grp[grp['modelo_key'].map(lambda m:family_match(name,m))]
            if len(valid):
                maxlen=valid['modelo_key'].str.len().max()
                valid=valid[valid['modelo_key'].str.len()==maxlen]
                candidates=list(valid.itertuples(index=False))
        for c in candidates:
            compatible=fuel_compat(v.combustivel_fipe,c.tecnologia)
            links.append({'veiculo_id':vehicle,'inmetro_id':c.inmetro_id,
                          'marca_fipe':v.marca_fipe,'modelo_fipe':v.modelo_fipe,
                          'ano_modelo':v.ano_modelo,'combustivel_fipe':v.combustivel_fipe,
                          'modelo_inmetro':c.modelo,'versao_inmetro':c.versao,
                          'tecnologia_inmetro':c.tecnologia,
                          'propulsao_compativel_preliminar':compatible,
                          'status_match':'PENDENTE_REVISAO_VERSAO' if compatible else 'ALERTA_PROPULSAO',
                          'consumo_atribuido_fipe':False,'evidencia_validacao':''})
        uber_valid=[]
        for _,u in ug.get(v.marca_key,pd.DataFrame()).iterrows():
            if not prefix_model(name,u.modelo_key): continue
            for cat,field in CATS.items():
                yr=pd.to_numeric(u[field],errors='coerce')
                if pd.isna(yr): continue
                estado='ANO_AUSENTE' if pd.isna(v.ano_num) else ('ANO_COMPATIVEL' if v.ano_num>=yr else 'ANO_INFERIOR')
                uber_rows.append({'veiculo_id':vehicle,'categoria_uber':cat,'modelo_uber':u['modelo'],
                                  'ano_min_lista':int(yr),'status_ano':estado,
                                  'elegibilidade_confirmada':False})
                if estado=='ANO_COMPATIVEL':uber_valid.append(cat)
        summaries.append({'veiculo_id':vehicle,'marca_fipe':v.marca_fipe,'modelo_fipe':v.modelo_fipe,
                          'ano_modelo':v.ano_modelo,'combustivel_fipe':v.combustivel_fipe,
                          'preco_fipe_rs':v.preco_fipe_rs,'referencia_fipe':v.mes_referencia,
                          'categorias_ano_compativel':';'.join(sorted(set(uber_valid))),
                          'quantidade_candidatos_inmetro_familia':len(candidates),
                          'quantidade_candidatos_propulsao_compativel':sum(fuel_compat(v.combustivel_fipe,c.tecnologia) for c in candidates),
                          'status_consumo':'NAO_HOMOLOGADO','consumo_inmetro_id_aprovado':'',
                          'custo_energia_rs_km_atribuido':'',
                          'status_calculo':'PENDENTE_HOMOLOGACAO'})
    catalog=pd.DataFrame(summaries)
    edges=pd.DataFrame(links,columns=['veiculo_id','inmetro_id','marca_fipe','modelo_fipe','ano_modelo',
                 'combustivel_fipe','modelo_inmetro','versao_inmetro','tecnologia_inmetro',
                 'propulsao_compativel_preliminar','status_match','consumo_atribuido_fipe','evidencia_validacao'])
    uber=pd.DataFrame(uber_rows,columns=['veiculo_id','categoria_uber','modelo_uber','ano_min_lista','status_ano','elegibilidade_confirmada'])
    products=an[an['municipio'].str.upper().str.strip().eq('SAO PAULO')]
    prices={r['produto'].strip().upper():num(r['preco_medio_rs_litro']) for _,r in products.iterrows()}
    gasoline=prices.get('GASOLINA COMUM'); ethanol=prices.get('ETANOL')
    if gasoline is None or ethanol is None or len(ae)!=1: raise ValueError('Preços ANP/ANEEL incompletos')
    electricity=num(ae.iloc[0]['tarifa_com_bandeira_rs_kwh'])
    if electricity is None: raise ValueError('Tarifa elétrica inválida')
    # Cenários da própria ficha INMETRO, separados da FIPE. Isso NÃO associa versão/ano.
    results=[]
    for _,r in im.iterrows():
        base_row={'inmetro_id':r['inmetro_id'],'marca_inmetro':r['marca'],'modelo_inmetro':r['modelo'],
                  'versao_inmetro':r['versao'],'tecnologia':r['tecnologia'],
                  'km_mes_hipotese':km,'eficiencia_recarga_hipotese':efficiency,
                  'origem_consumo':'INMETRO','tipo_calculo':'CENARIO_TECNICO_SEM_MATCH_FIPE',
                  'tarifa_eletrica_inclui_tributos':str(ae.iloc[0]['inclui_tributos']).lower()=='true'}
        for fuel,col,p in [('gasolina','consumo_gasolina_diesel_cidade_km_l',gasoline),
                           ('etanol','consumo_etanol_cidade_km_l',ethanol)]:
            if fuel=='gasolina' and norm(r['combustivel']) in ('D','DIESEL'):
                continue # não usar preço de gasolina para consumo diesel
            rate=num(r[col])
            if rate is not None and r['tecnologia'] in ('Combustao','Hibrido','Hibrido plug-in'):
                cost=p/rate
                results.append({**base_row,'modalidade':fuel,'consumo_original':rate,
                                'unidade_consumo_original':'km/l (cidade)','custo_energia_rs_km':round(cost,6),
                                'custo_energia_rs_mes':round(cost*km,2),
                                'observacoes':'Consumo urbano; não é custo operacional completo'})
        mj=num(r['consumo_energetico_mj_km'])
        if mj is not None and r['tecnologia']=='Eletrico':
            # PBEV MJ/km é um indicador energético regulatório; a conversão é aproximação
            # para cenário e NÃO substitui medição de kWh obtido da rede.
            kwh=mj/3.6
            cost=kwh*electricity/efficiency
            results.append({**base_row,'modalidade':'eletricidade',
                            'consumo_original':mj,'unidade_consumo_original':'MJ/km (PBEV)',
                            'custo_energia_rs_km':round(cost,6),'custo_energia_rs_mes':round(cost*km,2),
                            'observacoes':'Aproximação MJ/3,6 e eficiência hipotética; conferir definição regulatória/recarga'})
    calc=pd.DataFrame(results)
    out.mkdir(parents=True,exist_ok=True)
    files={'dim_veiculos_fipe.csv':catalog,'bridge_fipe_inmetro_pendente.csv':edges,
           'bridge_fipe_uber_ano.csv':uber,'fato_cenarios_inmetro_energia.csv':calc}
    for name,df in files.items(): df.to_csv(out/name,index=False,encoding='utf-8-sig')
    report={'executado_em':datetime.now().isoformat(timespec='seconds'),
            'referencia_fipe':'novembro de 2026',
            'registros_fipe':len(catalog),'familias_inmetro_com_candidatos':int((catalog['quantidade_candidatos_inmetro_familia']>0).sum()),
            'veiculos_com_ano_uber_compativel':int(catalog['categorias_ano_compativel'].ne('').sum()),
            'links_candidatos_inmetro':len(edges),'links_com_alerta_propulsao':int(edges['status_match'].eq('ALERTA_PROPULSAO').sum()),
            'consumos_homologados_fipe':0,'simulacoes_inmetro_por_combustivel':len(calc),
            'restricoes':['Nenhuma versão FIPE-INMETRO homologada automaticamente',
                          'Ano mínimo Uber não comprova elegibilidade real',
                          'MJ/km elétrico convertido para cenário aproximado, sem impostos e com recarga hipotética',
                          'Sem receita e custos complementares não há lucro líquido',
                          'Sem espacialização da frota por zona OD'],
            'parametros':{'km_mes':km,'eficiencia_recarga':efficiency,
                          'gasolina_rs_l':gasoline,'etanol_rs_l':ethanol,'tarifa_rs_kwh':electricity},
            'arquivos_gerados':list(files)}
    (out/'resumo_consolidacao.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2,ensure_ascii=False))
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raiz',type=Path,default=Path('.'))
    p.add_argument('--saida',type=Path,default=Path('dados_relatorios/consolidacao_integrada'))
    p.add_argument('--km-mes',type=int,default=3000)
    p.add_argument('--eficiencia-recarga',type=float,default=0.90)
    a=p.parse_args()
    run(a.raiz,a.saida,a.km_mes,a.eficiencia_recarga)
