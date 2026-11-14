"""PI06: fontes economicas complementares, sem contaminar os dados observados.

Uso (raiz do repo): python integrar_pesquisa_economica.py
Nao modifica cenarios_motorista.csv nem o motor economico.
Gera novo arquivo de perfis para uso opcional e resumos de ofertas locais.

Fonte de verdade: URLs no catalogo_premissas_economicas.csv e FONTES_E_LACUNAS.md.
"""
from __future__ import annotations
import argparse
import csv
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import json
from statistics import median

ROOT_OUTPUT = 'dados_relatorios/economia_pesquisa_2026'
PROFILE_FIELDS = [
 'perfil_id','regime','km_mes','horas_mes','receita_plataforma_liquida_rs_mes',
 'manutencao_rs_km','pneus_rs_km','lavagem_rs_mes','celular_rs_mes',
 'seguro_rs_mes','outros_fixos_rs_mes','ipva_efetivo_rs_ano','licenciamento_rs_ano',
 'depreciacao_rs_mes','aluguel_rs_mes','percentual_energia_pago_motorista',
 'percentual_manutencao_pago_motorista','percentual_pneus_pago_motorista',
 'percentual_seguro_pago_motorista','percentual_ipva_pago_motorista',
 'percentual_licenciamento_pago_motorista','fonte_premissas','observacoes'
]

# URLS verificados em pesquisa de 14/11/2026. Os valores de terceiros nao sao tabelas oficiais.
CATALOGO = [
 ('licenciamento_sp_2026','174.08','R$/ano','OFICIAL','SP','2026','Taxa estadual de licenciamento','https://servicos.sp.gov.br/fcarta/564F6C83-1A86-472E-AC79-3A7F5ABFE248'),
 ('aliquota_ipva_automovel_sp','0.04','fracao','OFICIAL_REGRA','SP','2026','Regra geral de automoveis proprios; 4% sobre base fiscal, sujeito a isencoes','https://legislacao.fazenda.sp.gov.br/Paginas/lei13296.aspx'),
 ('base_ipva_2026','', 'R$/veiculo','FONTE_SEM_MATCH','SP','2026','Base venal do IPVA 2026 publicada em tabela propria; nao usar FIPE novembro/2026 como base fiscal','https://legislacao.fazenda.sp.gov.br/Paginas/Resolu%C3%A7%C3%A3o-SFP-40-de-2025.aspx'),
 ('limite_isencao_hibridos_2026','261154.45','R$','OFICIAL_CONDICIONAL','SP','2026','Nao basta ser hibrido; verificar motorizacao flex/etanol 40kW e 150V, e enquadramento','https://www3.fazenda.sp.gov.br/SIPET/ServicosInstrucao/Instrucao/321'),
 ('incentivo_ipva_municipio_2026','', 'R$','NAO_APLICAVEL_GERAL','Capital SP','2025-2026','Pedido de reembolso suspenso para exercicios a partir de 2025','https://prefeitura.sp.gov.br/web/meio_ambiente/w/organizacao/265486'),
 ('das_mei_servicos_2026','86.05','R$/mes','OFICIAL_CONDICIONAL','Brasil','2026','Somente motorista enquadrado como MEI de servicos; nao somar a outro INSS automaticamente','https://www8.receita.fazenda.gov.br/SIMPLESNACIONAL/noticias/NoticiaCompleta.aspx?id=c3b2044c-ff97-432a-b33c-ecf2a3df6dc3'),
 ('rendimento_condutor_plataforma_ibge_2025','2873','R$/mes','OFICIAL_REFERENCIA_NAO_RECEITA','Brasil','2025','Rendimento apos despesas de atividade declaradas, NAO receita da plataforma para descontar custos','https://www.ibge.gov.br/estatisticas/sociais/trabalho/17270-pnad-continua.html?=&t=series-historicas'),
 ('horas_condutor_plataforma_ibge_2025','45.9','horas/semana','OFICIAL_REFERENCIA','Brasil','2025','Media nacional para condutores por plataformas','https://agenciabrasil.ebc.com.br/economia/noticia/2026-09/apenas-1-em-cada-5-motociclistas-de-app-tem-cobertura-previdenciaria'),
 ('seguro_uso_app_exemplo_onix','400','R$/mes','CENARIO_MERCADO_NAO_COTACAO','Sao Paulo','2026','Exemplo central ilustrativo Onix; ha intervalos e perfis distintos; cobertura total deve ser verificada','https://meegseg.com/seguro-para-motorista-de-aplicativo-uber-99/'),
 ('custo_manutencao_e_pneus_total','0.13','R$/km','CENARIO_MERCADO','Brasil','2026','Provisao ilustrativa 0.10 manutencao e 0.03 pneus, soma dentro de faixa 0.12-0.20 de terceiro','https://rodagem.com/blog/motorista-de-aplicativo-quanto-sobra-por-km/'),
 ('pneus_custo_central','0.03','R$/km','CENARIO_DERIVADO','Brasil','2026','Exemplo: 1400 reais por jogo / 50000 km = R$ 0.028/km; arredondado','https://clubers.app/'),
 ('recarga_residencial_enel_sem_tributos','0.78938','R$/kWh','OFICIAL_ARQUIVO_PROJETO','Capital SP','2026-11','Tarifa ANEEL Enel SP no projeto sem tributos; nao equivale ao valor total da conta','https://www.gov.br/aneel/pt-br/assuntos/tarifas'),
 ('recarga_publica_mediana_sp','2.10','R$/kWh','PESQUISA_MERCADO_TERCEIRO','Estado SP','2026-09','Mediana de 617 estacoes reportada por FLAK, metodologia nao auditada; variam taxas extras','https://flakenergy.com.br/guias/preco-da-recarga-de-carro-eletrico-em-sp'),
 ('recarga_publica_precificacao_livre','', 'regra','OFICIAL_REGRA','Brasil','2026','Cobrança livre por operadores; nao aplicar tarifa residencial nas recargas publicas','https://www.gov.br/aneel/pt-br/assuntos/veiculos-eletricos'),
 ('rental_uber_match_sp','', 'R$/mes','OFERTA_AMOSTRA_PROJETO','Sao Paulo','2026-11-07','Usar medianna de ofertas validas como contexto, nunca como aluguel garantido ou para todos os carros','https://earn.uber.com/en/city/sao-paulo-BR/458/rentals_category'),
 ('depreciacao_carro_especifico','', 'R$/mes','PENDENTE','SP','2026','Depende de serie FIPE para mesma versao/ano; cenarios de taxa percentual nao sao observacao','https://veiculos.fipe.org.br/'),
 ('receita_antes_de_custos_do_motorista','', 'R$/mes','PENDENTE','Capital SP','2026','Sem serie publica suficientemente comparavel para o campo do motor: nao usar media IBGE de rendimento','https://www.ibge.gov.br/estatisticas/sociais/trabalho/17270-pnad-continua.html?=&t=series-historicas'),
 ('lavagem_exemplo','80','R$/mes','HIPOTESE_AUTOR','SP','2026','Hipotese 2 lavagens por 40 reais, nao media apurada',''),
 ('celular_exemplo','50','R$/mes','HIPOTESE_AUTOR','SP','2026','Reserva para plano de dados; nao media apurada',''),
 ('quilometragem_cenario','3000','km/mes','HIPOTESE_MODELO_EXISTENTE','SP','2026','Valor usado no motor; nao media estatistica de motoristas',''),
 ('horas_cenario','200','h/mes','CENARIO_REFERENCIADO','Brasil','2026','Aproxima 45.9 horas por semana x 52/12 = 198.9 horas; use como cenario nao media paulista','https://agenciabrasil.ebc.com.br/economia/noticia/2026-09/apenas-1-em-cada-5-motociclistas-de-app-tem-cobertura-previdenciaria'),
]

def d(v):
    """Retorna Decimal positivo/zero com . ou formato BR. Nao aceita texto sujo."""
    s=str(v or '').strip().replace('R$', '').replace(' ', '')
    if not s or s.lower() in ('nan','null','none'): return None
    if ',' in s and '.' in s: s=s.replace('.','').replace(',','.')
    elif ',' in s: s=s.replace(',','.')
    try:
        n=Decimal(s)
        if not n.is_finite() or n<0: return None
        return n
    except InvalidOperation: return None

def yes(v):
    return str(v).strip().lower() in ('true','sim','s','1','yes')

def ler_csv(p):
    with p.open(newline='',encoding='utf-8-sig') as f: return list(csv.DictReader(f))

def write_csv(p,rows,fields,overwrite=False):
    if p.exists() and not overwrite: raise FileExistsError(f'Nao sobrescrever: {p}')
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)

def aluguel_validos(rows):
    """Somente anuncios aptos no snapshot, sem inferir confiabilidade atual."""
    valid=[]
    for row in rows:
        if row.get('tipo_oferta_fonte','').strip().lower()!='aluguel': continue
        if 'sao paulo' not in row.get('cidade','').lower() and 'são paulo' not in row.get('cidade','').lower(): continue
        if not yes(row.get('apto_modelo_economico')): continue
        if str(row.get('status_qualidade','')).strip().lower()!='ok': continue
        valor=d(row.get('valor_mensal_equivalente'))
        if valor is None or valor<=0: continue
        # Excluir anúncios de origem que declaram validade anterior a coleta requer revisao externa.
        # Nao inferir isso de texto livre, manter como condicao do snapshot.
        valid.append({'id_publico_oferta':row.get('id_publico_oferta',''),
             'veiculo':row.get('veiculo',''), 'locadora':row.get('locadora',''),
             'valor_mensal_rs':str(valor.quantize(Decimal('.01'),rounding=ROUND_HALF_UP)),
             'seguro_incluso_declarado':str(yes(row.get('seguro_incluso'))),
             'manutencao_inclusa_declarada':str(yes(row.get('manutencao_inclusa'))),
             'ipva_incluso_declarado':str(yes(row.get('ipva_incluso'))),
             'data_coleta':row.get('data_coleta',''), 'url_oferta':row.get('url_oferta','')})
    return valid

def criar_perfis():
    """Nenhum 'lucro' é liberado: receita, IPVA e depreciacao seguem pendentes."""
    own={name:'' for name in PROFILE_FIELDS}
    own.update(perfil_id='proprio_custo_referencial_2026',regime='proprio',km_mes='3000',horas_mes='200',
        manutencao_rs_km='0.10',pneus_rs_km='0.03',lavagem_rs_mes='80',celular_rs_mes='50',
        seguro_rs_mes='400',outros_fixos_rs_mes='86.05',licenciamento_rs_ano='174.08',
        percentual_energia_pago_motorista='1',percentual_manutencao_pago_motorista='1',
        percentual_pneus_pago_motorista='1',percentual_seguro_pago_motorista='1',
        percentual_ipva_pago_motorista='1',percentual_licenciamento_pago_motorista='1',
        fonte_premissas='CATALOGO_PESQUISA_2026-11; OFICIAL + CENARIO',
        observacoes=('SIMULACAO, nao custo real: seguro 400 e manutencao 0.10+pneus 0.03 referenciais; '
                     'lavagem e celular hipoteses; DAS 86.05 apenas se MEI servicos; '
                     'receita, IPVA individual e depreciacao nao preenchidos.'))
    # Nao associar aluguel real de um Kwid a TODOS os cenarios INMETRO.
    rental={name:'' for name in PROFILE_FIELDS}
    rental.update(perfil_id='alugado_pendente_contrato_2026',regime='alugado',km_mes='3000',horas_mes='200',
        lavagem_rs_mes='80',celular_rs_mes='50',outros_fixos_rs_mes='86.05',
        percentual_energia_pago_motorista='1',
        fonte_premissas='UBER_MATCH_SNAPSHOT_2026-11; HIPOTESES',
        observacoes=('Receita e aluguel vazios ate escolher contrato do MESMO modelo; '
                     'percentuais de manutencao pneus seguro IPVA licenciamento vazios '
                     'ate confirmar cobertura; DAS apenas para perfil MEI.'))
    return [own,rental]

def calcular_recarga_publica(rows,price=Decimal('2.10')):
    output=[]
    for row in rows:
        if row.get('modalidade','').strip().lower()!='eletricidade': continue
        if row.get('unidade_consumo_original','')!='MJ/km (PBEV)': continue
        mj=d(row.get('consumo_original'))
        eff=d(row.get('eficiencia_recarga_hipotese'))
        km=d(row.get('km_mes_hipotese'))
        if mj is None or eff is None or eff<=0 or km is None: continue
        c=mj/Decimal('3.6')/eff*price
        output.append({'inmetro_id':row.get('inmetro_id',''),
                'marca_inmetro':row.get('marca_inmetro',''),'modelo_inmetro':row.get('modelo_inmetro',''),
                'versao_inmetro':row.get('versao_inmetro',''),'km_mes':str(km),
                'consumo_energetico_mj_km':str(mj),'custo_publico_rs_kwh':str(price),
                'custo_publico_rs_km':str(c.quantize(Decimal('.000001'),rounding=ROUND_HALF_UP)),
                'custo_publico_rs_mes':str((c*km).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)),
                'tipo_referencia':'MEDIANA_TERCEIRO_SP_SET_2026; SIMULACAO_INMETRO_NAO_HOMOLOGADO_FIPE',
                'fonte_url':'https://flakenergy.com.br/guias/preco-da-recarga-de-carro-eletrico-em-sp'})
    return output

def executar(raiz:Path):
    out=raiz/ROOT_OUTPUT
    out.mkdir(parents=True,exist_ok=True)
    catfile=out/'catalogo_premissas_economicas.csv'
    out_rows=[dict(zip(['codigo','valor_referencia','unidade','qualidade','geografia','periodo','observacao','url_fonte'],x)) for x in CATALOGO]
    write_csv(catfile,out_rows,['codigo','valor_referencia','unidade','qualidade','geografia','periodo','observacao','url_fonte'],overwrite=True)

    # Arquivo NOVO que nunca substitui o arquivo original do usuario.
    profilefile=raiz/'dados_config/cenarios_motorista_pesquisa_2026.csv'
    estado_config='ja_existia_preservado'
    if not profilefile.exists():
        write_csv(profilefile,criar_perfis(),PROFILE_FIELDS)
        estado_config='criado'

    offerfile=raiz/'dados_limpos/17_UBER_MATCH_OFERTAS_SP.csv'
    a=[];medianvalue=None
    if offerfile.exists():
        a=aluguel_validos(ler_csv(offerfile))
        write_csv(out/'ofertas_aluguel_amostra_uber_match.csv',a,
                  ['id_publico_oferta','veiculo','locadora','valor_mensal_rs',
                   'seguro_incluso_declarado','manutencao_inclusa_declarada',
                   'ipva_incluso_declarado','data_coleta','url_oferta'],overwrite=True)
        if a: medianvalue=round(median([float(x['valor_mensal_rs']) for x in a]),2)

    scenariofile=raiz/'dados_relatorios/consolidacao_integrada/fato_cenarios_inmetro_energia.csv'
    e=[]
    if scenariofile.exists():
        e=calcular_recarga_publica(ler_csv(scenariofile))
        write_csv(out/'cenario_recarga_publica_sp.csv',e,
          ['inmetro_id','marca_inmetro','modelo_inmetro','versao_inmetro','km_mes',
           'consumo_energetico_mj_km','custo_publico_rs_kwh','custo_publico_rs_km',
           'custo_publico_rs_mes','tipo_referencia','fonte_url'],overwrite=True)

    report={
        'status':'PESQUISA_CONSOLIDADA_COM_LACUNAS_DECLARADAS',
        'fontes_e_premissas':len(out_rows),
        'perfis_novos':len(criar_perfis()),
        'config_referencial':str(profilefile),'config_estado':estado_config,
        'ofertas_uber_match_aptas_no_snapshot':len(a),
        'mediana_amostral_aluguel_rs_mes':medianvalue,
        'linhas_cenario_recarga_publica':len(e),
        'continuam_sem_dado_individual':['receita antes dos custos de plataforma','IPVA fiscal de cada carro e isencoes',
          'depreciacao por versao FIPE/ano','premio de seguro por veiculo e condutor','aluguel contratado do mesmo modelo',
          'manutencao especifica de cada motorizacao','tributos finais da conta de eletricidade'],
        'restricoes':['Nao alterou o motor nem a configuracao original','Medianas de ofertas nao sao contratos vigentes',
          'Rendimento IBGE nao e receita bruta','Custos referenciais nao sao observados',
          'Recarga publica e cenario aproximado, sem taxas de sessao',
          'Nenhum vinculo FIPE-INMETRO aprovado automaticamente']
    }
    (out/'resumo_fontes_economicas.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raiz',type=Path,default=Path('.'))
    args=parser.parse_args()
    executar(args.raiz)
