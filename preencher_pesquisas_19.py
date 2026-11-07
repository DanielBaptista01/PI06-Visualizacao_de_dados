"""PI06 | registra pesquisas auditáveis e preenche somente campos verificáveis.

Uso: python preencher_pesquisas_19.py [--raiz RAIZ_PROJETO]
Não faz consultas web, não altera dados brutos e não substitui parâmetros existentes.
Pesquisa congelada em 07/11/2026; reconfirmar preços para simulações futuras.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

CAMPOS_COTACOES = ['categoria','veiculo_marca_modelo_versao','localidade','valor_brl','unidade',
                   'data_referencia','url_fonte','tipo_fonte','perfil_ou_condicoes','status_validacao']
DATA='2026-11-07'

def registro(categoria,veiculo,valor,unidade,url,tipo,condicoes,status='observado_com_ressalvas',local='São Paulo'):
    return dict(zip(CAMPOS_COTACOES,[categoria,veiculo,local,valor,unidade,DATA,url,tipo,condicoes,status]))

FONTES = [
    registro('licenciamento','AUTOMOVEL SP 2026',174.08,'BRL/ano',
        'https://servicos.sp.gov.br/fcarta/1DD2C9F8-815F-49D4-9D47-F09885256ECE','governo_sp',
        'Taxa oficial do licenciamento exercício 2026; já calculada no modelo econômico; NÃO somar outra vez','oficial'),
    registro('pneus','FIAT MOBI LIKE 1.0',349.90,'BRL/pneu',
        'https://www.lojacontinentalpneus.com.br/pneu-continental-aro-14-contipowercontact-175-65r14-82t-10120002',
        'loja_fabricante','Pneu novo ContiPowerContact 175/65R14 82T; preço anunciado sem promoção, uma unidade. Quatro unidades R$ 1399,60; montagem/frete e desgaste não inclusos'),
    registro('pneus','BYD DOLPHIN MINI GS EV',389.84,'BRL/pneu',
        'https://www.kdpneus.com.br/pneus/pneu-wanli-aro-16-17555r16-sp022-80h-pneu-byd-dolphin-mini',
        'loja_pneus','Wanli SP022 175/55R16 80H novo, preço com desconto à vista (R$389,84); quatro unidades R$1559,36 sem frete/instalação; confirmar compatibilidade do índice'),
    registro('manutencao_programada','BYD DOLPHIN MINI GS EV',8576.00,'BRL/10_revisoes_200000km',
        'https://www.byd.com/br/plano-de-manutencao-2026','fabricante',
        'Soma oficial sugerida de 10 revisões até 200.000 km, vigente desde 01/09/2026; equivalente parcial de R$0,04288/km. NÃO cobre toda manutenção nem reparos extraordinários. Não copiar como custo total/km','oficial_preco_sugerido'),
    registro('energia_tarifa_base','RESIDENCIAL B1 ENEL SP',0.78938,'BRL/kWh',
        'https://www.enel.com.br/pt-saopaulo/Para_Voce/tarifa-energia-eletrica.html','distribuidora',
        'TE R$316,96/MWh + TUSD R$472,42/MWh = R$0,78938/kWh; válida desde 04/07/2026. SEM tributos/bandeira/outros encargos; NÃO é preço final da conta','base_sem_tributos'),
    registro('recarga_publica_mediana','ESTACOES PAGAS ESTADO SP',2.10,'BRL/kWh',
        'https://flakenergy.com.br/guias/preco-da-recarga-de-carro-eletrico-em-sp','pesquisa_setorial',
        'Mediana de 617 estações pagas no estado de SP, levantamento setembro/2026; não é preço de posto específico; taxas adicionais variam','mediana_estadual_nao_operador'),
]
FICHAS = [
    {'marca':'BYD','modelo':'DOLPHIN MINI','versao':'GS EV','pneu_medida':'175/55 R16',
     'url_medida':'https://www.byd.com/content/dam/byd-site/br/flyer/ficha-tecnica-dolphinini_v3.pdf',
     'status':'medida_fabricante_por_modelo_confirmar_versao'},
    {'marca':'FIAT','modelo':'MOBI','versao':'LIKE','pneu_medida':'175/65 R14 82T',
     'url_medida':'https://www.conti.com.br/about-us/why-continental/original-equipment/pneu-original-fiat/pneu-original-fiat-mobi/',
     'status':'medida_fabricante_pneus_confirmar_ano_versao'},
]

def _ler(path):
    return pd.read_csv(path,dtype='string',keep_default_na=False,encoding='utf-8-sig')

def _salvar(path,frame):
    frame.to_csv(path,index=False,encoding='utf-8-sig')

def _posicao(ref,marca,modelo,versao):
    if not {'veiculo_id_inmetro','marca','modelo','versao'}.issubset(ref.columns):
        raise ValueError('referencia_veiculos_inmetro.csv sem chaves esperadas')
    mask=(ref.marca.str.strip().str.upper().eq(marca)&ref.modelo.str.strip().str.upper().eq(modelo)
          &ref.versao.str.strip().str.upper().eq(versao))
    found=ref.loc[mask]
    return found.iloc[0] if len(found)==1 else None

def _set_if_blank(df,idx,col,value):
    if value is None or str(value)=='' or col not in df.columns:
        return False
    if str(df.at[idx,col]).strip()!='':
        return False
    df.at[idx,col]=str(value)
    return True

def _exportar_anp(raiz,folder):
    """Gera candidatos de preços observados na cidade de São Paulo, sem transformar preço de posto em média."""
    anp=raiz/'dados_padronizados'/'03_ANP_SP.csv'
    if not anp.exists(): return 'ANP não localizada; sem candidatos'
    df=pd.read_csv(anp,low_memory=False,encoding='utf-8-sig')
    import unicodedata
    def key(s):
        x=unicodedata.normalize('NFKD',str(s))
        return ''.join(c for c in x if not unicodedata.combining(c)).upper().replace('_',' ').strip()
    keys={key(c):c for c in df.columns}
    city=next((v for k,v in keys.items() if k in ('MUNICIPIO','MUNICÍPIO','CIDADE')),None)
    product=next((v for k,v in keys.items() if k in ('PRODUTO','COMBUSTIVEL','COMBUSTÍVEL')),None)
    if city is None or product is None:
        return f'ANP localizada; cidade/produto sem reconhecimento: {df.columns.tolist()}'
    normalize=lambda x: ''.join(c for c in unicodedata.normalize('NFKD',str(x)) if not unicodedata.combining(c)).upper().strip()
    filtro=(df[city].map(normalize).eq('SAO PAULO') &
             df[product].map(normalize).str.contains('GASOLINA|ETANOL',regex=True,na=False))
    subset=df.loc[filtro].copy()
    out=folder/'pesquisas_19_anp_sp_observacoes_candidatas.csv'
    subset.to_csv(out,index=False,encoding='utf-8-sig')
    return f'ANP observações de postos em São Paulo (gasolina/etanol): {len(subset)}; NÃO é média e pode haver várias semanas'

def executar(raiz):
    folder=raiz/'dados_complementares'/'etapa19'
    if not (folder/'parametros_cenarios.csv').is_file() or not (folder/'cotacoes.csv').is_file():
        raise FileNotFoundError('Primeiro executar: python consolidar_variaveis_19.py')
    cit=_ler(folder/'cotacoes.csv')
    cols=set(CAMPOS_COTACOES)
    if not cols.issubset(cit.columns): raise ValueError(f'Cotacoes sem campos {cols-set(cit.columns)}')
    input_rows=[]
    added=0
    for quote in FONTES:
        eq=(cit['categoria'].eq(quote['categoria'])&cit['veiculo_marca_modelo_versao'].eq(quote['veiculo_marca_modelo_versao'])&cit['url_fonte'].eq(quote['url_fonte']))
        if not eq.any():
            input_rows.append(quote)
            added+=1
    if input_rows:
        cit=pd.DataFrame(cit.to_dict('records')+input_rows,columns=list(cit.columns))
        _salvar(folder/'cotacoes.csv',cit)

    cen=_ler(folder/'parametros_cenarios.csv')
    if not {'cenario_id','modalidade'}.issubset(cen): raise ValueError('CSV de cenarios incompleto')
    ref=_ler(folder/'referencia_veiculos_inmetro.csv')
    dados={'proprio_eletrico':('BYD','DOLPHIN MINI','GS EV',389.84*4),
           'proprio_combustao':('FIAT','MOBI','LIKE',349.90*4)}
    updated=[]
    for idx,row in cen.iterrows():
        modal=str(row['modalidade']).strip()
        if modal not in dados: continue
        marca,modelo,versao,jogo=dados[modal]
        v=_posicao(ref,marca,modelo,versao)
        if v is None:
            updated.append({'cenario_id':row['cenario_id'],'status':'sem_versao_unica_INMETRO','marca':marca,'modelo':modelo,'versao':versao})
            continue
        ident=str(v['veiculo_id_inmetro'])
        current=str(cen.at[idx,'veiculo_id_inmetro']).strip()
        if current and current!=ident:
            updated.append({'cenario_id':row['cenario_id'],'status':'veiculo_previamente_selecionado_preservado','id':current})
            continue
        _set_if_blank(cen,idx,'veiculo_id_inmetro',ident)
        _set_if_blank(cen,idx,'jogo_pneus_brl',round(jogo,2))
        # Unicamente consumo elétrico puro. Para o Fiat, precisa escolher gasolina ou etanol.
        if modal=='proprio_eletrico':
            try:
                consumo=float(str(v.get('consumo_eletrico_kwh_km_referencia','')).strip())
            except (ValueError,TypeError): consumo=None
            if consumo is not None and 0<consumo<2:
                _set_if_blank(cen,idx,'consumo_eletrico_kwh_km',round(consumo,8))
        obs=str(cen.at[idx,'observacoes']) if 'observacoes' in cen else ''
        nota=f'Pesquisa 07/11/2026: {marca} {modelo} {versao}; pneu cotado por 4 unidades, frete/montagem fora; durabilidade não confirmada. Valores dependem de confirmação de versão.'
        if 'observacoes' in cen and nota not in obs:
            cen.at[idx,'observacoes']=(obs+' | '+nota).strip(' |')
        updated.append({'cenario_id':row['cenario_id'],'status':'preenchimento_parcial_seguro','id':ident})
    _salvar(folder/'parametros_cenarios.csv',cen)
    anp_status=_exportar_anp(raiz,folder)
    target=folder/'pesquisas_19_fichas_pneus.csv'
    _salvar(target,pd.DataFrame(FICHAS))
    pendencias=[
       ('seguro_brl_ano','cotação para motorista de app e perfil de risco; preço não pode ser universal','pendente_cotacao_individual'),
       ('manutencao_brl_km','cotar revisões completas + reparos e desgaste, por versão','referencia_parcial_BYD'),
       ('durabilidade_pneus_km','hipótese documentada por modelo, uso e rodagem','pendente_hipotese'),
       ('preco_energia_brl_kwh','TE+TUSD obtidos; faltam tributos/bandeira e distribuição válida','referencia_parcial'),
       ('preco_combustivel_brl_l','selecionar linha/agregado ANP do mesmo município, produto e data','disponivel_noutra_base'),
       ('ipva_brl_ano_confirmado','vincular código IPVA, modelo e ano; não aplicar isenção automática','ponte_a_validar'),
       ('depreciacao_brl_mes','requer preços históricos da MESMA versão','pendente_series'),
       ('receita_brl_por_hora_online','coleta observada ou hipótese explícita de cenário','pendente_metodologia'),
       ('km_mes','hipótese operacional para turno e região do usuário','pendente_hipotese'),
       ('horas_online_mes','hipótese operacional (online inclui espera)','pendente_hipotese'),
       ('outros_custos_brl_mes','definir escopo de estacionamento, limpeza, tributos e plataformas','pendente_escopo'),
    ]
    _salvar(folder/'pesquisas_19_pendencias_confirmacao.csv',pd.DataFrame(pendencias,columns=['campo','metodo_obtencao','status']))
    manifest={'gerado_utc':datetime.now(timezone.utc).isoformat(),'fontes_pesquisadas':len(FONTES),
              'cotacoes_acrescentadas':added,'cenarios_verificados':updated,'anp_status':anp_status,
              'politica':'Não preencher receita, seguro, manutenção total, desgaste de pneus e tarifa final sem evidência; não substituir dados já preenchidos.'}
    (folder/'pesquisas_19_manifesto.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'[OK] Pesquisas auditáveis: {len(FONTES)} | novas cotações: {added}')
    print('[ANP]',anp_status)
    for row in updated: print('[CENARIO]',row)
    print('[PENDENTE] Seguro, receita, durabilidade pneus, depreciação e demais hipóteses sem fonte específica.')
    print(f'[OK] Saídas preservadas em {folder}')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raiz',type=Path,default=Path(__file__).resolve().parent)
    a=parser.parse_args()
    executar(a.raiz.expanduser().resolve())
