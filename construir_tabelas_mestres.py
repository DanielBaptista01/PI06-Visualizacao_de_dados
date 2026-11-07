"""PI06 — camada mestre por domínio (somente leitura de dados_padronizados).

Uso: python construir_tabelas_mestres.py
     python construir_tabelas_mestres.py --validar

Não altera fontes existentes. Publica uma versão imutável em
    dados_mestres/execucoes/<identificador>/
e atualiza dados_mestres/atual.json somente após TODAS as validações.

Não realiza merges globais, imputações nem inferência de elegibilidade Uber.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
import unicodedata
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
ENTRADA = ROOT / 'dados_padronizados'
SAIDA = ROOT / 'dados_mestres'
VERSOES = SAIDA / 'execucoes'

# Cada tabela guarda a granularidade da fonte; apenas os dois IBGEs
# se combinam numa dimensão por código IBGE, validada antes da escrita.
@dataclass(frozen=True)
class Fonte:
    arquivo: str
    dominio: str
    saida: str
    granularidade: str
    obrigatorias: tuple[str, ...]
    chave: tuple[str, ...] = ()

FONTES = (
    Fonte('05_INMETRO_ORGANIZADO.csv','veiculos','dim_modelos_versoes_inmetro.csv','linha da planilha organizada INMETRO',('marca','modelo','versao','linha_origem_excel'),('linha_origem_excel',)),
    Fonte('08_FIPE_VEICULOS_PARCIAL.csv','veiculos','fato_cotacoes_fipe_parcial.csv','versão FIPE × ano-modelo × mês de referência',('brand_id','model_id','year_code','mes_referencia','preco_fipe_brl'),('brand_id','model_id','year_code','mes_referencia')),
    Fonte('09_UBER_MODELOS_SP.csv','uber','regra_modelos_uber.csv','marca × modelo e critérios de ano mínimo por categoria',('marca','modelo')),
    Fonte('17_UBER_MATCH_OFERTAS_SP.csv','uber','fato_ofertas_locacao_uber.csv','oferta comercial individual',('id_publico_oferta','valor_reais_num','status_qualidade'),('id_publico_oferta',)),
    Fonte('10_OPEN_CHARGE_MAP_SP.csv','recarga','dim_pontos_recarga_ocm.csv','ponto cadastrado com localização',('id_posto','latitude_num','longitude_num'),('id_posto',)),
    Fonte('15_ABVE_ELETROPOSTOS_RMSP.csv','recarga','fato_totais_recarga_abve_municipios.csv','agregado por município ABVE (não pontos OCM)',('Municipio','Total_Eletropostos')),
    Fonte('17_ABVE_EVOLUCAO_ELETROPOSTOS_SP.csv','recarga','fato_serie_recarga_abve.csv','ano × mês da evolução declarada',('Ano','Mês','Total_Eletropostos')),
    Fonte('07_ORIGEM_DESTINO.csv','mobilidade','fato_viagens_aplicativo_od2023.csv','registro amostral de viagem; peso FE_VIA',('MODOPRIN','FE_VIA')),
    Fonte('03_ANP_SP.csv','energia','fato_pesquisas_precos_anp_sp.csv','observação de preço de revenda/produto/data',('Produto','Valor de Venda','preco_venda_brl_por_unidade_num')),
    Fonte('02_ANEEL_NACIONAL.csv','energia','fato_tarifas_aneel_nacional.csv','distribuidora × vigência × modalidade × posto × unidade',()),
    Fonte('06_SENATRAN_ANO_SP.csv','frota','fato_frota_senatran_ano.csv','frota por município/ano e demais dimensões',('Município',)),
    Fonte('06_SENATRAN_CEP_SP.csv','frota','fato_frota_senatran_cep.csv','frota por município/CEP e demais dimensões',('Município',)),
    Fonte('06_SENATRAN_COMBUSTIVEL_SP.csv','frota','fato_frota_senatran_combustivel.csv','frota por município/combustível',('Município','Combustível Veículo')),
    Fonte('06_SENATRAN_MARCA_MODELO_SP.csv','frota','fato_frota_senatran_marca_modelo.csv','frota por município/marca-modelo',('Município',)),
    Fonte('06_SENATRAN_POTENCIA_SP.csv','frota','fato_frota_senatran_potencia.csv','frota por município/potência',('Município',)),
    Fonte('06_SENATRAN_TIPO_VEICULO_SP.csv','frota','fato_frota_senatran_tipo.csv','frota municipal por tipos em colunas',('MUNICIPIO','TOTAL')),
    Fonte('11_ABVE_VENDAS_RMSP.csv','mercado','fato_vendas_abve_rmsp.csv','agregado de vendas por município RMSP',('Municipio','Quantidade')),
    Fonte('11_ABVE_VENDAS_SAO_PAULO.csv','mercado','fato_vendas_abve_capital.csv','agregado de vendas municipal da capital; visão sobreposta à RMSP',('Municipio','Quantidade')),
    Fonte('14_ABVE_VENDAS_POR_MODELO.csv','mercado','fato_vendas_abve_modelos.csv','ano × mês × fabricante × modelo',('Ano','Mês','Fabricante','Modelo','Quantidade')),
    Fonte('16_ABVE_VENDAS_MHEV_BRASIL.csv','mercado','fato_vendas_mhev_brasil.csv','vendas MHEV por município no recorte Brasil',('Municipio','Quantidade_MHEV')),
    Fonte('16_ABVE_VENDAS_MHEV_RMSP.csv','mercado','fato_vendas_mhev_rmsp.csv','vendas MHEV por município RMSP',('Municipio','Quantidade_MHEV')),
    Fonte('16_ABVE_VENDAS_MHEV_SAO_PAULO.csv','mercado','fato_vendas_mhev_capital.csv','vendas MHEV municipal da capital; visão sobreposta',('Municipio','Quantidade_MHEV')),
    Fonte('abve_resumo_tecnologia.csv','mercado','fato_serie_abve_tecnologia.csv','ano × mês × tecnologia (quantidade/share de significado misto)',('Ano','Mês','Tipo_Tecnologia','Quantidade_ou_Share')),
)

IBGE_SP='04_IBGE_SP.csv'
IBGE_RMSP='04_IBGE_RMSP.csv'
NA_TEXTO={'','ND','N/D','NA','N A','N.A.','N.A','NÃO INFORMADO','NAO INFORMADO','NULO','NULL','NAN','-','—','–','\\'}


def chave_texto(v: object) -> str:
    if v is None or pd.isna(v):
        return ''
    t = unicodedata.normalize('NFKD', str(v).strip().upper())
    t = ''.join(c for c in t if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', re.sub(r'[^A-Z0-9]+', ' ', t)).strip()


def vazio(v: object) -> bool:
    return chave_texto(v) in NA_TEXTO


def ler(nome: str, necessarias: tuple[str, ...] = ()) -> pd.DataFrame:
    caminho=ENTRADA/nome
    if not caminho.is_file():
        raise FileNotFoundError(f'Arquivo padronizado não encontrado: {caminho}')
    df=pd.read_csv(caminho, encoding='utf-8-sig', dtype='string', keep_default_na=False, low_memory=False)
    if not len(df):
        raise ValueError(f'{nome}: arquivo sem registros')
    if df.columns.duplicated().any():
        raise ValueError(f'{nome}: colunas duplicadas')
    faltando=sorted(set(necessarias)-set(df.columns))
    if faltando:
        raise ValueError(f'{nome}: faltam colunas {faltando}')
    return df


def sha256(caminho: Path) -> str:
    h=hashlib.sha256()
    with caminho.open('rb') as f:
        for bloco in iter(lambda:f.read(1024*1024),b''):
            h.update(bloco)
    return h.hexdigest()


def verificar_chave(df:pd.DataFrame, campos:tuple[str,...], titulo:str) -> None:
    if not campos:return
    for col in campos:
        if df[col].astype(object).map(vazio).astype(bool).any():
            raise ValueError(f'{titulo}: chave incompleta em {col}')
    n=int(df.duplicated(list(campos)).sum())
    if n:
        raise ValueError(f'{titulo}: {n} chaves {campos} duplicadas')


def salvar(df:pd.DataFrame,caminho:Path) -> None:
    caminho.parent.mkdir(parents=True,exist_ok=True)
    df.to_csv(caminho,index=False,encoding='utf-8-sig')
    # Releitura real: conteúdo CSV pode incluir linhas internas em textos.
    import csv
    with caminho.open(encoding='utf-8-sig',newline='') as f:
        reader=csv.reader(f)
        header=next(reader)
        rows=sum(1 for _ in reader)
    if rows!=len(df) or len(header)!=len(df.columns):
        raise ValueError(f'Arquivo gerado inconsistente: {caminho}')


def lista_relacao_municipio(df:pd.DataFrame,fonte:Fonte,lookup:dict[str,str]) ->tuple[pd.Series,pd.Series]:
    """Só liga nomes municipais quando o contexto é comprovadamente SP.

    Dados do Brasil podem conter cidades homônimas: exige Estado=SP.
    """
    if 'municipio_chave' not in df.columns:
        return pd.Series(['']*len(df),index=df.index,dtype='string'),pd.Series(['nao_aplicavel']*len(df),index=df.index,dtype='string')
    nome=df['municipio_chave'].map(chave_texto)
    nome_ambito_sp=fonte.arquivo not in {'16_ABVE_VENDAS_MHEV_BRASIL.csv'}
    if nome_ambito_sp:
        sp=pd.Series(True,index=df.index)
    else:
        # Brasil: confirmar UF explícita em cada linha para evitar homônimos.
        campo='Estado' if 'Estado' in df.columns else 'UF' if 'UF' in df.columns else None
        sp=(df[campo].map(chave_texto).isin({'SP','SAO PAULO'}) if campo else pd.Series(False,index=df.index))
    codigo=nome.map(lookup).where(sp,'').fillna('').astype('string')
    status=pd.Series('nao_encontrado_no_ibge_sp',index=df.index,dtype='string')
    status.loc[~sp]='fora_do_escopo_sp_ou_uf_incerta'
    status.loc[codigo.ne('')]='exato_nome_e_uf_sp'
    status.loc[nome.eq('')]='nome_ausente'
    return codigo,status


def construir_municipios(sp:pd.DataFrame,rmsp:pd.DataFrame) ->tuple[pd.DataFrame,dict[str,str]]:
    verificar_chave(sp,('CD_MUN',),'IBGE SP')
    verificar_chave(rmsp,('CD_MUN',),'IBGE RMSP')
    if not set(rmsp['CD_MUN']).issubset(set(sp['CD_MUN'])):
        raise ValueError('RMSP contém código municipal ausente da base IBGE SP')
    cols={'CD_MUN','NM_MUN','SIGLA_UF'}
    if not cols.issubset(sp.columns):raise ValueError('IBGE SP sem CD_MUN, NM_MUN ou SIGLA_UF')
    dim=sp.copy()
    dim['codigo_ibge_municipio']=dim['CD_MUN']
    dim['municipio_chave']=dim['NM_MUN'].map(chave_texto).astype('string')
    if dim['municipio_chave'].duplicated().any():
        raise ValueError('Há municípios SP com nome normalizado duplicado; vínculo por nome é ambíguo')
    dim['pertence_rmsp']=dim['CD_MUN'].isin(set(rmsp['CD_MUN']))
    dim['origem_cadastro']='IBGE / 04_IBGE_SP.csv'
    assert len(dim)==len(sp)
    lookup=dict(zip(dim['municipio_chave'],dim['CD_MUN']))
    return dim,lookup


def uber_marca_normalizada(v:object) ->str:
    # Erro de extração confirmado: "AcuraDown" é marca "Acura" + ícone Down.
    # Limita-se à tabela Uber; não altera a coluna original nem outras fontes.
    t=chave_texto(v)
    if t.endswith('DOWN') and len(t)>4:
        t=t[:-4].strip()
    return t


def id_indice(prefixo:str, df:pd.DataFrame)->pd.Series:
    return pd.Series((f'{prefixo}:{i}' for i in range(1,len(df)+1)),index=df.index,dtype='string')


def construir_pontes(uber:pd.DataFrame, inmetro:pd.DataFrame, fipe:pd.DataFrame)->tuple[pd.DataFrame,pd.DataFrame,pd.DataFrame]:
    """Pontes de *candidatos*: nunca atribuem elegibilidade ou identidade por versão."""
    u=uber[['id_registro_mestre','marca','modelo']].copy()
    u['marca_comparacao']=u['marca'].map(uber_marca_normalizada)
    u['modelo_comparacao']=u['modelo'].map(chave_texto)
    i=inmetro[['id_registro_mestre','marca','modelo','versao']].copy()
    i['marca_comparacao']=i['marca'].map(chave_texto)
    i['modelo_comparacao']=i['modelo'].map(chave_texto)
    f=fipe[['id_registro_mestre','marca_fipe','modelo_fipe','mes_referencia']].copy()
    f['marca_comparacao']=f['marca_fipe'].map(chave_texto)
    f['modelo_comparacao']=f['modelo_fipe'].map(chave_texto)
    # Proteção contra muitas correspondências de um modelo só por marca.
    u=u.loc[u['marca_comparacao'].ne('')&u['modelo_comparacao'].ne('')]
    i=i.loc[i['marca_comparacao'].ne('')&i['modelo_comparacao'].ne('')]
    f=f.loc[f['marca_comparacao'].ne('')&f['modelo_comparacao'].ne('')]
    lk=['marca_comparacao','modelo_comparacao']
    ponte_i=u.merge(i,how='inner',on=lk,validate='many_to_many',suffixes=('_uber','_inmetro'))
    ponte_i=ponte_i.rename(columns={'id_registro_mestre_uber':'id_modelo_uber','id_registro_mestre_inmetro':'id_versao_inmetro'})
    ponte_i['tipo_correspondencia']='candidato_exato_marca_modelo_sem_confirmacao_de_versao'
    ponte_f=u.merge(f,how='inner',on=lk,validate='many_to_many',suffixes=('_uber','_fipe'))
    ponte_f=ponte_f.rename(columns={'id_registro_mestre_uber':'id_modelo_uber','id_registro_mestre_fipe':'id_cotacao_fipe'})
    ponte_f['tipo_correspondencia']='candidato_exato_marca_modelo_sem_confirmacao_de_versao_ano'
    # Classifica cobertura por número de linhas candidatas; não chama "match confirmado".
    ni=ponte_i.groupby('id_modelo_uber').size().to_dict() if len(ponte_i) else {}
    nf=ponte_f.groupby('id_modelo_uber').size().to_dict() if len(ponte_f) else {}
    cobertura=uber[['id_registro_mestre','marca','modelo']].rename(columns={'id_registro_mestre':'id_modelo_uber'}).copy()
    cobertura['candidatos_inmetro']=cobertura['id_modelo_uber'].map(ni).fillna(0).astype('int64')
    cobertura['candidatos_fipe']=cobertura['id_modelo_uber'].map(nf).fillna(0).astype('int64')
    cobertura['status_inmetro']=cobertura['candidatos_inmetro'].map(lambda n:'sem_candidato_exato' if n==0 else 'um_candidato_sem_confirmacao' if n==1 else 'multiplas_versoes_ou_registros')
    cobertura['status_fipe']=cobertura['candidatos_fipe'].map(lambda n:'sem_candidato_exato' if n==0 else 'uma_cotacao_sem_confirmacao' if n==1 else 'multiplas_cotacoes_ano_versao')
    if not set(ponte_i.get('id_versao_inmetro',pd.Series([],dtype='string'))).issubset(set(inmetro['id_registro_mestre'])):
        raise ValueError('FK INMETRO inválida na ponte')
    if not set(ponte_f.get('id_cotacao_fipe',pd.Series([],dtype='string'))).issubset(set(fipe['id_registro_mestre'])):
        raise ValueError('FK FIPE inválida na ponte')
    return ponte_i,ponte_f,cobertura


def dicionario_tabelas(fonte:Fonte|None,relpath:str,df:pd.DataFrame)->list[dict]:
    return [{'arquivo_tabela':relpath,'coluna':c,'tipo_exportado':str(df[c].dtype),
             'ausentes_e_marcadores':int(df[c].astype(object).map(vazio).astype(bool).sum()) if c!='id_registro_mestre' else 0,
             'granularidade':fonte.granularidade if fonte else 'tabela derivada de múltiplas fontes, conforme documentação',
             'fonte_original':fonte.arquivo if fonte else 'derivada (ver relatório)',
             'variavel_derivada':c in {'id_registro_mestre','linha_csv_origem','codigo_ibge_municipio','status_vinculo_ibge','pertence_rmsp','marca_comparacao','modelo_comparacao','candidatos_fipe','candidatos_inmetro','status_inmetro','status_fipe','tipo_correspondencia'}} for c in df.columns]


def construir(validar:bool=False)->Path|None:
    if not ENTRADA.exists():raise FileNotFoundError(f'Execute primeiro padronizar_bases.py. Pasta ausente: {ENTRADA}')
    n_utc=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    versao=f'{n_utc}_{uuid.uuid4().hex[:8]}'
    VERSOES.mkdir(parents=True,exist_ok=True)
    registros=[];dic=[];avisos=[];lacunas=[];base={};estatisticas_municipais=[]
    # Estágio privado com commit apenas após todas as validações.
    with tempfile.TemporaryDirectory(prefix='pi06_mestres_') as tmp:
        p=Path(tmp)/versao
        p.mkdir()
        sp=ler(IBGE_SP,('CD_MUN','NM_MUN','SIGLA_UF'))
        rmsp=ler(IBGE_RMSP,('CD_MUN','NM_MUN','SIGLA_UF'))
        dim,municipios=construir_municipios(sp,rmsp)
        salvar(dim,p/'territorios'/'dim_municipios_sp.csv')
        dic.extend(dicionario_tabelas(None,'territorios/dim_municipios_sp.csv',dim))
        registros.append({'dominio':'territorios','tabela':'territorios/dim_municipios_sp.csv','arquivo_origem':f'{IBGE_SP} + {IBGE_RMSP}','linhas':len(dim),'hash_origem':f'{sha256(ENTRADA/IBGE_SP)};{sha256(ENTRADA/IBGE_RMSP)}','granularidade':'um município IBGE SP'})
        total_vinculos=Counter()
        for fonte in FONTES:
            x=ler(fonte.arquivo,fonte.obrigatorias)
            verificar_chave(x,fonte.chave,fonte.arquivo)
            if fonte.arquivo == '02_ANEEL_NACIONAL.csv':
                # O CSV padronizado pode utilizar o esquema oficial atual,
                # distinto dos títulos legados Sigla/Início Vigência/Unidade.
                # Sem dicionário validado, mantemos as colunas originais e
                # registramos a pendência sem afirmar granularidade comprovada.
                nomes = {chave_texto(c) for c in x.columns}
                tarifas = {'TE', 'TUSD', 'TE NUM', 'TUSD NUM', 'VLRTE', 'VLRTUSD', 'VLR TE', 'VLR TUSD'}
                datas = {'INICIO VIGENCIA', 'DAT INICIO VIGENCIA', 'DATINICIOVIGENCIA', 'DATA INICIO VIGENCIA'}
                unidade = {'UNIDADE', 'DSC UNIDADE', 'DSCUNIDADE', 'UNIDADE MEDIDA', 'DSC UNIDADE TARIFARIA'}
                presentes = {
                    'tarifas': bool(nomes & tarifas),
                    'vigencia': bool(nomes & datas),
                    'unidade': bool(nomes & unidade),
                }
                if not all(presentes.values()):
                    ausentes = [campo for campo, encontrado in presentes.items() if not encontrado]
                    avisos.append('ANEEL: preservada sem interpretação semântica completa. '
                                  f'Dimensões não identificadas automaticamente: {ausentes}. '
                                  f'Colunas disponíveis: {list(x.columns)}. '
                                  'Não usar em cálculo econômico até conferir o esquema oficial.')
                    lacunas.append({
                        'dominio':'energia', 'variavel':'identificação de tarifas, vigência e unidade ANEEL',
                        'linhas_afetadas':len(x), 'tipo':'esquema não confirmado',
                        'acao':'conferir colunas da versão atual, unidade e vigência; não inferir TE/TUSD',
                    })
            x['id_registro_mestre']=id_indice(fonte.saida.replace('.csv',''),x)
            x['linha_csv_origem']=pd.Series(range(2,len(x)+2),index=x.index,dtype='Int64')
            if fonte.arquivo=='09_UBER_MODELOS_SP.csv':
                x['marca_comparacao']=x['marca'].map(uber_marca_normalizada).astype('string')
                x['modelo_comparacao']=x['modelo'].map(chave_texto).astype('string')
                avisos.append('Uber: sufixo HTML "Down" removido APENAS em marca_comparacao; marca original mantida.')
            if fonte.arquivo=='10_OPEN_CHARGE_MAP_SP.csv':
                recorte='recorte_geografico'
                if recorte not in x or not x[recorte].eq('municipio_sao_paulo_ibge_3550308').all():
                    raise ValueError('OCM: recorte municipal incompatível com o validado na etapa 1.8')
                x['codigo_ibge_municipio']='3550308'
                x['status_vinculo_ibge']='recorte_geografico_3550308';total_vinculos.update({'recorte_geografico_3550308':len(x)})
            elif fonte.arquivo=='17_UBER_MATCH_OFERTAS_SP.csv':
                if 'cidade' in x:
                    x['codigo_ibge_municipio']=x['cidade'].map(lambda v: municipios.get(chave_texto(v),'') if chave_texto(v)=='SAO PAULO' else '').astype('string')
                    x['status_vinculo_ibge']=x['codigo_ibge_municipio'].map(lambda c:'exato_cidade_declarada' if c else 'nao_associado')
            elif 'municipio_chave' in x:
                x['codigo_ibge_municipio'],x['status_vinculo_ibge']=lista_relacao_municipio(x,fonte,municipios)
                total_vinculos.update(x['status_vinculo_ibge'].value_counts().to_dict())
            if 'status_vinculo_ibge' in x:
                for status, n_status in x['status_vinculo_ibge'].value_counts(dropna=False).items():
                    estatisticas_municipais.append({'fonte':fonte.arquivo,'status':status,'linhas':int(n_status),'percentual':round(100*int(n_status)/len(x),2)})
            caminho_rel=f'{fonte.dominio}/{fonte.saida}'
            salvar(x,p/caminho_rel)
            base[fonte.arquivo]=x if fonte.arquivo in {'05_INMETRO_ORGANIZADO.csv','08_FIPE_VEICULOS_PARCIAL.csv','09_UBER_MODELOS_SP.csv'} else None
            registros.append({'dominio':fonte.dominio,'tabela':caminho_rel,'arquivo_origem':fonte.arquivo,'linhas':len(x),'hash_origem':sha256(ENTRADA/fonte.arquivo),'granularidade':fonte.granularidade})
            dic.extend(dicionario_tabelas(fonte,caminho_rel,x))
            print(f'[OK] {fonte.dominio}/{fonte.saida}: {len(x)} linhas')
        ponte_i,ponte_f,cobertura=construir_pontes(base['09_UBER_MODELOS_SP.csv'],base['05_INMETRO_ORGANIZADO.csv'],base['08_FIPE_VEICULOS_PARCIAL.csv'])
        for rel, df in [('relacionamentos/ponte_candidatos_uber_inmetro.csv',ponte_i),('relacionamentos/ponte_candidatos_uber_fipe.csv',ponte_f),('relacionamentos/cobertura_modelos_uber.csv',cobertura)]:
            salvar(df,p/rel)
            registros.append({'dominio':'relacionamentos','tabela':rel,'arquivo_origem':'candidatos Uber + INMETRO/FIPE (não confirmado)','linhas':len(df),'hash_origem':'derivado','granularidade':'candidatos ou cobertura por linha de modelo Uber'})
            dic.extend(dicionario_tabelas(None,rel,df))
        # Lacunas observáveis e advertências importantes da arquitetura.
        n_sem_i=int(cobertura['candidatos_inmetro'].eq(0).sum());n_sem_f=int(cobertura['candidatos_fipe'].eq(0).sum())
        lacunas.extend([
            {'dominio':'veiculos','variavel':'correspondência Uber ↔ INMETRO por versão','linhas_afetadas':n_sem_i,'tipo':'cobertura de matching exato por modelo','acao':'revisão por versão, motorização e ano; não assumir elegibilidade'},
            {'dominio':'veiculos','variavel':'correspondência Uber ↔ FIPE por versão/ano','linhas_afetadas':n_sem_f,'tipo':'cobertura de matching exato por modelo','acao':'coleta FIPE parcial; validar versão, combustível, ano e mês'},
            {'dominio':'territorios','variavel':'código Zona OD de cada ponto de recarga','linhas_afetadas':'a avaliar','tipo':'requer dado espacial','acao':'usar polígono oficial das zonas OD 2023 com join espacial e CRS explícito'},
            {'dominio':'energia','variavel':'tarifa residencial SP vigente R$/kWh','linhas_afetadas':'a avaliar','tipo':'filtro e validade temporal','acao':'confirmar distribuidora, unidade, modalidade, subgrupo, tributos e vigência na ANEEL'},
            {'dominio':'energia','variavel':'preço público de recarga por kWh','linhas_afetadas':'a avaliar','tipo':'variável não observada para todos os pontos','acao':'pesquisar fonte comercial verificável, data e unidade'},
            {'dominio':'modelo_economico','variavel':'receita do motorista, manutenção, seguro, IPVA, depreciação','linhas_afetadas':'a avaliar','tipo':'parâmetros externos','acao':'pesquisar na etapa 1.9; não atribuir valor 0'},
            {'dominio':'mercado','variavel':'período e abrangência de certas séries ABVE','linhas_afetadas':'a avaliar','tipo':'metadados insuficientes','acao':'confirmar documento original e denominadores de market share'},
        ])
        salvar(pd.DataFrame(lacunas),p/'relatorios'/'lacunas_variaveis.csv')
        salvar(pd.DataFrame(dic),p/'relatorios'/'dicionario_tabelas_mestres.csv')
        qualidade=pd.DataFrame(dic)
        total_linhas_por_tabela={r['tabela']:r['linhas'] for r in registros}
        qualidade['linhas_tabela']=qualidade['arquivo_tabela'].map(total_linhas_por_tabela)
        qualidade['percentual_ausente']=((100*qualidade['ausentes_e_marcadores']/qualidade['linhas_tabela']).round(2))
        salvar(qualidade.loc[qualidade['ausentes_e_marcadores'].gt(0)].sort_values(['percentual_ausente','arquivo_tabela'],ascending=[False,True]),p/'relatorios'/'qualidade_campos_com_ausencias.csv')
        if estatisticas_municipais:
            salvar(pd.DataFrame(estatisticas_municipais),p/'relatorios'/'cobertura_vinculos_municipais.csv')
        salvar(pd.DataFrame(registros),p/'relatorios'/'inventario_tabelas.csv')
        for k,v in total_vinculos.items():
            if k!='exato_nome_e_uf_sp' and k!='recorte_geografico_3550308':
                avisos.append(f'Vínculos municipais com status {k}: {v} linhas (não ligados automaticamente).')
        avisos.extend([
            'A origem IBGE RMSP marca pertença ao conjunto de 39 municípios, não gera zonas OD.',
            'As pontes Uber-INMETRO e Uber-FIPE são candidatas somente por marca/modelo EXATO normalizado; NÃO comprovam versão, ano ou categoria elegível.',
            'A FIPE é parcial; ausência de candidato NÃO significa ausência de preço na tabela FIPE completa.',
            'Os dados SENATRAN são fatos distintos por dimensão, não somar suas tabelas entre si.',
            'ABVE capital está contida em recortes mais amplos; não somar vistas capital + RMSP + Brasil.',
            'ANEEL nacional tem vigências/unidades distintas (R$/kW e R$/kWh); não calcular custo por kWh ainda.',
            'OD registra amostras expandidas por FE_VIA; distância pode ser em linha reta e não percurso real.',
            'Recarga OCM (pontos) não equivale à quantidade agregada de carregadores da ABVE.',
            'Sem tabelas de fotos/imagens de eletropostos: nenhuma fonte de fotos validada foi fornecida.',
            'Para georreferenciar Zonas OD é preciso cruzamento espacial com a geometria oficial de zonas OD; não imputar zonas por nome de município.',
        ])
        doc=['# PI06 — Tabelas-mestras específicas por domínio','',f'Gerado em UTC: {datetime.now(timezone.utc).isoformat()}','','## Política de modelagem','- Uma tabela por entidade, evento ou granularidade verificável; nenhuma tabela gigante.','- Todos os CSVs de entrada em dados_padronizados permanecem sem alterações.','- Zero não substitui ND/ausente; saídas mantêm colunas originais.','- `id_registro_mestre` identifica somente a linha da respectiva fonte/versão. Não representa identidade universal de veículo.','- `linha_csv_origem` permite rastrear a posição no arquivo, considerando cabeçalho na linha 1.','- Tabelas de escopo nacional, estadual, municipal e pontual não são propagadas para Zonas OD sem vínculo validado.','','## Catálogo de domínios']
        for r in registros:doc.append(f"- `{r['tabela']}` — {r['linhas']} linhas; {r['granularidade']}")
        doc+=['','## Alertas e limites de integração']+[f'- {a}' for a in avisos]
        doc+=['','## Próximas ações','1. Revisar `relacionamentos/cobertura_modelos_uber.csv` e as pontes; não converter candidatos em confirmações automaticamente.','2. Incorporar malha das Zonas OD para relações espaciais com pontos de recarga.','3. Pesquisar lacunas da etapa 1.9 usando `relatorios/lacunas_variaveis.csv`.','4. Publicar dimensões e fatos no PostgreSQL/PostGIS apenas após aprovar chaves e cargas.']
        (p/'README.md').write_text('\n'.join(doc)+'\n',encoding='utf-8')
        manifesto={'gerado_em_utc':datetime.now(timezone.utc).isoformat(),'versao':versao,'validacao_apenas':validar,'fontes_esperadas':len(FONTES)+2,'tabelas_geradas':len(registros),'fontes':registros,'limites':avisos}
        (p/'manifesto.json').write_text(json.dumps(manifesto,indent=2,ensure_ascii=False),encoding='utf-8')
        # Verifica entrega completa ANTES de mover os arquivos ao diretório definitivo.
        if len(registros)!=len(FONTES)+4:
            raise ValueError(f'Inventário incompleto: {len(registros)} tabelas; esperado {len(FONTES)+4}')
        if validar:
            print(f'\n[VALIDADO] {len(registros)} tabelas em diretório temporário. Nenhuma publicação efetuada.')
            return None
        final=VERSOES/versao
        shutil.copytree(p,final)
        # Aponta a nova versão somente após cópia e validação de inventário.
        SAIDA.mkdir(parents=True,exist_ok=True)
        pointer=SAIDA/'atual.json'
        tmp_pointer=SAIDA/'.atual.json.tmp'
        tmp_pointer.write_text(json.dumps({'versao':versao,'pasta':f'execucoes/{versao}','gerado_em_utc':manifesto['gerado_em_utc']},indent=2,ensure_ascii=False),encoding='utf-8')
        tmp_pointer.replace(pointer)
        print(f'\n[PUBLICADO] {len(registros)} tabelas em {final}')
        print(f'[ATUAL] {pointer}')
        return final


def main()->int:
    parser=argparse.ArgumentParser(description='Gera tabelas por domínio, com integridade e proveniência')
    parser.add_argument('--validar',action='store_true',help='Executa validação e escrita temporária sem publicar')
    a=parser.parse_args()
    try:
        construir(validar=a.validar)
        return 0
    except (ValueError,FileNotFoundError,KeyError,OSError,pd.errors.ParserError) as exc:
        print(f'\n[ERRO BLOQUEANTE] {exc}',file=sys.stderr)
        print('Nenhuma versão nova foi apontada em dados_mestres/atual.json.',file=sys.stderr)
        return 1

if __name__=='__main__':
    raise SystemExit(main())
