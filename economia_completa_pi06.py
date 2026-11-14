"""PI06 - Bloco económico completo por cenários técnicos INMETRO.
Não assume matching FIPE-INMETRO nem elegibilidade Uber. Python 3.10+, pandas.
Uso: python economia_completa_pi06.py --gerar-config
     edite dados_config/cenarios_motorista.csv
     python economia_completa_pi06.py
"""
from __future__ import annotations
import argparse
import csv
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
import pandas as pd

FIELDS = [
 'perfil_id','regime','km_mes','horas_mes','receita_plataforma_liquida_rs_mes',
 'manutencao_rs_km','pneus_rs_km','lavagem_rs_mes','celular_rs_mes',
 'seguro_rs_mes','outros_fixos_rs_mes','ipva_efetivo_rs_ano','licenciamento_rs_ano',
 'depreciacao_rs_mes','aluguel_rs_mes','percentual_energia_pago_motorista',
 'percentual_manutencao_pago_motorista','percentual_pneus_pago_motorista',
 'percentual_seguro_pago_motorista','percentual_ipva_pago_motorista',
 'percentual_licenciamento_pago_motorista','fonte_premissas','observacoes'
]
MODES={'proprio','alugado'}

def d(x, field='numero', optional=True):
    if x is None or pd.isna(x) or str(x).strip().lower() in ('','nan','none','null'):
        if optional: return None
        raise ValueError(f'{field} obrigatório')
    val=str(x).strip().replace('R$','').replace(' ','')
    if ',' in val and '.' in val: val=val.replace('.','').replace(',','.')
    elif ',' in val: val=val.replace(',','.')
    try: result=Decimal(val)
    except InvalidOperation: raise ValueError(f'{field}: número inválido: {x!r}')
    if not result.is_finite() or result<0: raise ValueError(f'{field}: deve ser finito e >= 0')
    return result

def ratio(x, field, default=None):
    val=d(x,field)
    if val is None: val=default
    if val is None: return None
    if val<0 or val>1: raise ValueError(f'{field} deve estar entre 0 e 1')
    return val

def numstr(x):
    return '' if x is None else str(x.quantize(Decimal('.000001')))

def template(path:Path):
    if path.exists(): raise FileExistsError(f'Não sobrescreverei {path}')
    path.parent.mkdir(parents=True,exist_ok=True)
    profiles=[{'perfil_id':'proprio_base','regime':'proprio','km_mes':'3000', 'horas_mes':'200',
               'percentual_energia_pago_motorista':'1', 'percentual_manutencao_pago_motorista':'1',
               'percentual_pneus_pago_motorista':'1','percentual_seguro_pago_motorista':'1',
               'percentual_ipva_pago_motorista':'1','percentual_licenciamento_pago_motorista':'1',
               'fonte_premissas':'PARAMETROS_A_PREENCHER'},
              {'perfil_id':'alugado_base','regime':'alugado','km_mes':'3000','horas_mes':'200',
               'percentual_energia_pago_motorista':'1',
               'fonte_premissas':'CONTRATO_A_CONFERIR'}]
    with path.open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS); w.writeheader(); w.writerows(profiles)
    return path

def optional_sum(values):
    return sum(values,Decimal(0)) if all(v is not None for v in values) else None

def times(a,b): return None if a is None or b is None else a*b

def result(profile, row):
    pid=profile['perfil_id']
    regime=profile['regime'].strip().lower()
    if regime not in MODES: raise ValueError(f'{pid}: regime inválido: {regime}; financiamento exige módulo separado')
    km=d(profile['km_mes'],'km_mes',False)
    if km<=0: raise ValueError('km_mes deve ser maior que zero')
    horas=d(profile.get('horas_mes'),'horas_mes')
    if horas==0: raise ValueError('horas_mes deve ser > 0 ou vazio')
    receita=d(profile.get('receita_plataforma_liquida_rs_mes'),'receita_plataforma_liquida_rs_mes')
    # A coluna financeira nasce de cenário INMETRO, não de um carro FIPE validado.
    e=d(row['custo_energia_rs_km'],'custo_energia_rs_km',False)
    energia_pct=ratio(profile.get('percentual_energia_pago_motorista'),'percentual_energia_pago_motorista')
    maint_pct=ratio(profile.get('percentual_manutencao_pago_motorista'),'percentual_manutencao_pago_motorista')
    tyre_pct=ratio(profile.get('percentual_pneus_pago_motorista'),'percentual_pneus_pago_motorista')
    seguro_pct=ratio(profile.get('percentual_seguro_pago_motorista'),'percentual_seguro_pago_motorista')
    ipva_pct=ratio(profile.get('percentual_ipva_pago_motorista'),'percentual_ipva_pago_motorista')
    lic_pct=ratio(profile.get('percentual_licenciamento_pago_motorista'),'percentual_licenciamento_pago_motorista')
    # Se uma parcela não é paga pelo motorista, seu valor não precisa ser informado.
    def share(field,pct,div=Decimal(1),scale=Decimal(1)):
        if pct==0: return Decimal(0)
        v=d(profile.get(field),field)
        return v*pct*scale/div if v is not None else None
    custo_energia=e*km*energia_pct if energia_pct is not None else None
    manut=share('manutencao_rs_km',maint_pct,scale=km) if maint_pct is not None else None
    pneus=share('pneus_rs_km',tyre_pct,scale=km) if tyre_pct is not None else None
    seguro=share('seguro_rs_mes',seguro_pct) if seguro_pct is not None else None
    ipva=share('ipva_efetivo_rs_ano',ipva_pct,div=Decimal(12)) if ipva_pct is not None else None
    lic=share('licenciamento_rs_ano',lic_pct,div=Decimal(12)) if lic_pct is not None else None
    lavagem=d(profile.get('lavagem_rs_mes'),'lavagem_rs_mes')
    celular=d(profile.get('celular_rs_mes'),'celular_rs_mes')
    outros=d(profile.get('outros_fixos_rs_mes'),'outros_fixos_rs_mes')
    deprec=d(profile.get('depreciacao_rs_mes'),'depreciacao_rs_mes') if regime=='proprio' else Decimal(0)
    aluguel=d(profile.get('aluguel_rs_mes'),'aluguel_rs_mes') if regime=='alugado' else Decimal(0)
    # Resultado económico: depreciação do bem próprio; no aluguel, aluguel substitui depreciação.
    # Não há prestação financeira porque principal e juros não podem ser tratados juntos como custo económico.
    componentes=[custo_energia,manut,pneus,seguro,ipva,lic,lavagem,celular,outros,deprec,aluguel]
    total=optional_sum(componentes)
    resultado=receita-total if receita is not None and total is not None else None
    missing=[]
    names=['energia','manutencao','pneus','seguro','ipva','licenciamento','lavagem','celular','outros_fixos','depreciacao','aluguel']
    missing.extend(name for name,v in zip(names,componentes) if v is None)
    if receita is None: missing.append('receita_motorista')
    return {
      'perfil_id':pid,'regime':regime,'inmetro_id':row['inmetro_id'],
      'marca_inmetro':row.get('marca_inmetro',''),'modelo_inmetro':row.get('modelo_inmetro',''),
      'versao_inmetro':row.get('versao_inmetro',''),'tecnologia':row.get('tecnologia',''),
      'modalidade':row.get('modalidade',''),'km_mes':numstr(km),
      'receita_liquida_plataforma_rs_mes':numstr(receita),
      'custo_energia_rs_mes':numstr(custo_energia),
      'custo_manutencao_rs_mes':numstr(manut),'custo_pneus_rs_mes':numstr(pneus),
      'custo_seguro_rs_mes':numstr(seguro),'custo_ipva_rs_mes':numstr(ipva),
      'custo_licenciamento_rs_mes':numstr(lic),'custo_lavagem_rs_mes':numstr(lavagem),
      'custo_celular_rs_mes':numstr(celular),'custo_outros_fixos_rs_mes':numstr(outros),
      'custo_depreciacao_rs_mes':numstr(deprec),'custo_aluguel_rs_mes':numstr(aluguel),
      'custo_total_economico_rs_mes':numstr(total),
      'resultado_economico_rs_mes':numstr(resultado),
      'custo_total_rs_km':numstr(total/km if total is not None else None),
      'receita_equilibrio_rs_km':numstr(total/km if total is not None else None),
      'receita_equilibrio_rs_hora':numstr(total/horas if total is not None and horas is not None else None),
      'status':'COMPLETO_CENARIO' if not missing else 'PARCIAL_PENDENTE',
      'campos_pendentes':';'.join(missing),
      'origem_consumo':'INMETRO_CENARIO_SEM_MATCH_FIPE',
      'fonte_premissas':profile.get('fonte_premissas',''),
      'observacoes':profile.get('observacoes','')}

def run(root:Path,config:Path,out:Path):
    source=root/'dados_relatorios/consolidacao_integrada/fato_cenarios_inmetro_energia.csv'
    if not source.is_file(): raise FileNotFoundError(f'Execute consolidar_pi06.py primeiro: {source}')
    if not config.is_file(): raise FileNotFoundError(f'Crie o CSV com --gerar-config: {config}')
    scenarios=pd.read_csv(source,dtype=str,keep_default_na=False,encoding='utf-8-sig')
    profiles=pd.read_csv(config,dtype=str,keep_default_na=False,encoding='utf-8-sig')
    for col in ['inmetro_id','modalidade','custo_energia_rs_km']:
        if col not in scenarios: raise ValueError(f'Arquivo económico sem {col}')
    for col in FIELDS:
        if col not in profiles: raise ValueError(f'Config sem {col}')
    if profiles.empty or scenarios.empty: raise ValueError('Perfis/cenários vazios')
    if profiles['perfil_id'].eq('').any() or profiles['perfil_id'].duplicated().any():
        raise ValueError('perfil_id obrigatório e único')
    rows=[result(p,r) for _,p in profiles.iterrows() for _,r in scenarios.iterrows()]
    table=pd.DataFrame(rows)
    out.mkdir(parents=True,exist_ok=True)
    output=out/'fato_cenarios_motorista.csv'
    table.to_csv(output,index=False,encoding='utf-8-sig')
    pending=(table['status']=='PARCIAL_PENDENTE').sum()
    report={'executado_em':datetime.now().isoformat(timespec='seconds'),
            'perfis':len(profiles),'cenarios_inmetro':len(scenarios),
            'linhas_geradas':len(table),'cenarios_completos':int(len(table)-pending),
            'cenarios_pendentes':int(pending),
            'arquivo_saida':str(output),
            'notas':['Simulações INMETRO, sem atribuição automática a FIPE',
                     'Receita é recebimento do motorista após taxas da plataforma, se preenchida',
                     'Valores vazios não são interpretados como zero',
                     'Licenciamento e IPVA só entram mediante valores informados e responsabilidade do motorista',
                     'Aluguel não inclui depreciação do automóvel; financiamento não é modelado aqui',
                     'Tributação pessoal, custos de oportunidade, financiamento e cobertura contratual não são inferidos']}
    (out/'resumo_economia_completa.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2,ensure_ascii=False))
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raiz',type=Path,default=Path('.'))
    p.add_argument('--config',type=Path,default=Path('dados_config/cenarios_motorista.csv'))
    p.add_argument('--saida',type=Path,default=Path('dados_relatorios/economia_completa'))
    p.add_argument('--gerar-config',action='store_true')
    a=p.parse_args()
    if a.gerar_config: print('Template criado:',template(a.raiz/a.config))
    else: run(a.raiz,a.raiz/a.config,a.raiz/a.saida)
