"""PI06 — etapa 1.9: catálogo, parâmetros verificáveis e preparação econômica.

Comando: python consolidar_variaveis_19.py [--raiz DIRETORIO]
Reexecução segura: não sobrescreve parâmetros_cenarios.csv nem cotacoes.csv.
Somente dados_complementares/etapa19 são criados/atualizados.

AVISO: resultado líquido só é publicado se TODOS os custos obrigatórios
forem informados e a receita corresponder a horas ONLINE (não hora em corrida).
Nenhuma média sem fonte é criada; renda líquida publicada por estudos nunca é
tratada como receita bruta.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REFERENCIAS = [
    ("detran_sp_2026", "Detran-SP", "taxa_licenciamento", "2026", "SP",
     "174.08", "BRL/ano", "oficial",
     "https://servicos.sp.gov.br/fcarta/1DD2C9F8-815F-49D4-9D47-F09885256ECE",
     "Atualização do serviço: 13/10/2026; não inclui multas/IPVA"),
    ("susep_seguro", "SUSEP", "premio_seguro", "consulta_2026", "Brasil",
     "", "BRL/ano", "metodologia",
     "https://www.gov.br/susep/pt-br/copy_of_planos-e-produtos/seguros/seguro-de-automoveis",
     "Preço depende de condutor, uso profissional, veículo, cobertura e local"),
    ("inmetro_energia", "INMETRO", "consumo_energetico", "2026", "Brasil",
     "", "MJ/km", "metodologia_oficial",
     "https://www.gov.br/inmetro/pt-br/acesso-a-informacao/perguntas-frequentes/avaliacao-da-conformidade/etiquetagem-para-veiculos-leves/como-e-calculado-o-consumo-dos-carros-eletricos/",
     "Para elétrico a bateria: MJ/km / 3,6 = kWh/km; não pressupor perda de recarga"),
    ("anp_preco", "ANP", "preco_combustivel", "por_coleta", "municipios_pesquisados",
     "", "BRL/litro", "pesquisa_semanal",
     "https://www.gov.br/anp/pt-br/assuntos/precos-e-defesa-da-concorrencia/precos/precos-revenda-e-de-distribuicao-combustiveis",
     "A pesquisa possui datas e municípios; não usar média como preço universal"),
    ("cebrap_amobitec_2025", "Cebrap/Amobitec", "referencia_remuneracao_motorista", "maio_2023_abril_2024", "Brasil",
     "3083 a 4400", "BRL/mes_liquido_40h_semana", "pesquisa_setorial",
     "https://amobitec.org/cresce-35-o-numero-de-motoristas-e-18-os-entregadores-que-trabalham-com-apps-no-brasil-revela-cebrap/",
     "Renda líquida mensal estimada de motoristas 40 h/semana; NÃO é receita bruta e NÃO deve alimentar fórmula de receita; pesquisa setorial apoiada pela associação"),
]

VARIAVEIS = [
    ("licenciamento_sp_2026", "tributos", "oficial", "174.08", "BRL/ano", "veiculo_proprio_em_SP", "detran_sp_2026", "pronto_com_condicao"),
    ("ipva_2026", "tributos", "arquivo_ipva_separado", "", "BRL/ano", "veiculo_modelo_ano_e_regime", "IPVA SP 2026", "depende_vinculo_ipva_confirmado"),
    ("seguro_profissional", "seguro", "cotacao_externa", "", "BRL/ano", "perfil_veiculo_uso_regiao", "susep_seguro", "pendente_cotacao"),
    ("manutencao", "manutencao", "revisoes_fabricante_ou_oficina", "", "BRL/km", "veiculo_versao_quilometragem", "fabricante_oficina", "pendente_cotacao"),
    ("pneus", "pneus", "preco_e_durabilidade", "", "BRL/km", "dimensao_pneu_e_uso", "loja_fabricante", "pendente_cotacao"),
    ("energia_domiciliar", "energia", "tarifa_completa", "", "BRL/kWh", "distribuidora_tarifa_tributos", "aneel_conta", "pendente_tarifa_efetiva"),
    ("recarga_publica", "energia", "tarifa_operador", "", "BRL/kWh", "operador_local_e_data", "operador_recarga", "pendente_cotacao"),
    ("combustivel", "energia", "anp_preco_observado", "", "BRL/litro", "municipio_produto_data", "anp_preco", "disponivel_para_selecao_temporal"),
    ("depreciacao", "depreciacao", "historico_comparavel", "", "BRL/mes", "mesma_versao_e_referencia", "fipe_historica", "pendente_serie_comparavel"),
    ("receita_efetiva", "receita", "hipotese_ou_dado_observado", "", "BRL/hora_online", "perfil_categoria_territorio_horario", "cebrap_amobitec_2025", "pendente_parametro"),
    ("aluguel", "aluguel", "oferta_uber_match", "", "BRL/mes", "contrato_data_veiculo", "uber_match", "disponivel_para_oferta_especifica"),
    ("horas_online", "operacao", "hipotese", "", "horas/mes", "cenario", "hipotese_explicita", "pendente_parametro"),
    ("distancia_mensal", "operacao", "hipotese", "", "km/mes", "cenario", "hipotese_explicita", "pendente_parametro"),
]

CENARIO_COLS = [
    'cenario_id','modalidade','veiculo_id_inmetro','oferta_uber_id','km_mes','horas_online_mes',
    'receita_brl_por_hora_online','preco_combustivel_brl_l','eficiencia_combustivel_km_l',
    'preco_energia_brl_kwh','consumo_eletrico_kwh_km','perda_recarga_pct',
    'seguro_brl_ano','manutencao_brl_km','jogo_pneus_brl','durabilidade_pneus_km',
    'ipva_brl_ano_confirmado','depreciacao_brl_mes','outros_custos_brl_mes',
    'seguro_incluido_contrato','manutencao_incluida_contrato','ipva_incluido_contrato',
    'licenciamento_incluido_contrato','fonte_parametros','observacoes'
]

COTACOES_COLS = ['categoria','veiculo_marca_modelo_versao','localidade','valor_brl','unidade',
                 'data_referencia','url_fonte','tipo_fonte','perfil_ou_condicoes','status_validacao']


def _write(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding='utf-8-sig')


def _number(value: object, *, nonnegative: bool = True) -> float | None:
    if pd.isna(value) or str(value).strip() == '':
        return None
    text = str(value).strip().replace('R$', '').replace(' ', '').replace('\u00a0', '')
    # explicit Brazilian formatting, or already-normalized machine number
    if ',' in text:
        text = text.replace('.', '').replace(',', '.')
    try:
        n = float(text)
    except (ValueError, TypeError) as exc:
        raise ValueError(f'Valor numérico inválido: {value!r}') from exc
    if not math.isfinite(n) or (nonnegative and n < 0):
        raise ValueError(f'Valor fora da faixa permitida: {value!r}')
    return n


def _boolean(value: object) -> bool | None:
    if pd.isna(value) or str(value).strip() == '':
        return None
    val = str(value).strip().lower()
    if val in ('true','1','sim','s'):
        return True
    if val in ('false','0','nao','não','n'):
        return False
    raise ValueError(f'Booleano inválido: {value!r}; use sim/nao/em branco')


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def _localizar_mestre(raiz: Path) -> tuple[Path | None, str | None]:
    pointer = raiz / 'dados_mestres' / 'atual.json'
    if not pointer.exists():
        return None, None
    data = json.loads(pointer.read_text(encoding='utf-8-sig'))
    part = data.get('pasta')
    if not isinstance(part, str) or not part.startswith('execucoes/') or '..' in Path(part).parts:
        raise ValueError('Ponteiro dados_mestres/atual.json inválido')
    folder = (raiz / 'dados_mestres' / part).resolve()
    if not folder.is_relative_to((raiz / 'dados_mestres').resolve()):
        raise ValueError('Ponteiro mestre fora da pasta autorizada')
    return folder, str(data.get('versao', ''))


def _veiculos(folder: Path | None) -> pd.DataFrame:
    columns = ['veiculo_id_inmetro','marca','modelo','versao','tipo_propulsao','consumo_energetico_mj_km_num','consumo_eletrico_kwh_km_referencia','observacao']
    if folder is None:
        return pd.DataFrame(columns=columns)
    file = folder / 'veiculos' / 'dim_modelos_versoes_inmetro.csv'
    if not file.is_file():
        return pd.DataFrame(columns=columns)
    data = pd.read_csv(file, low_memory=False)
    required = {'marca','modelo','versao','tipo_propulsao'}
    if required - set(data.columns):
        raise ValueError('Tabela mestre INMETRO sem colunas obrigatórias')
    data = data.copy()
    data['veiculo_id_inmetro'] = [f'INMETRO:{i + 1}' for i in range(len(data))]
    col = 'consumo_energetico_mj_km_num'
    if col not in data:
        data[col] = pd.NA
    data[col] = pd.to_numeric(data[col], errors='coerce')
    kinds = data['tipo_propulsao'].astype('string').str.upper().fillna('')
    # Only all-electric vehicles; do not treat combustion/hybrid MJ as electric kWh.
    electric = kinds.isin(['ELÉTRICO','ELETRICO'])
    data['consumo_eletrico_kwh_km_referencia'] = (data[col] / 3.6).where(electric)
    data['observacao'] = 'MJ/km convertido em kWh/km somente para eletrico; confirmar contexto de ensaio e perdas'
    return data[columns]


def _ofertas(folder: Path | None) -> pd.DataFrame:
    cols = ['id_publico_oferta','veiculo','locadora','valor_mensal_equivalente',
            'apto_modelo_economico','seguro_incluso','manutencao_inclusa','ipva_incluso','data_coleta','url_oferta']
    if folder is None:
        return pd.DataFrame(columns=cols)
    file = folder / 'uber' / 'fato_ofertas_locacao_uber.csv'
    if not file.is_file():
        return pd.DataFrame(columns=cols)
    df = pd.read_csv(file, low_memory=False, dtype={'id_publico_oferta':'string'})
    missing = set(cols) - set(df.columns)
    if missing:
        raise ValueError(f'Ofertas sem colunas necessárias: {sorted(missing)}')
    return df[cols].copy()


def _template_cenarios(path: Path) -> None:
    if path.exists():
        return
    values = []
    for key, mod in [('proprio_combustao','proprio_combustao'),('proprio_eletrico','proprio_eletrico'),('alugado','alugado')]:
        item = dict.fromkeys(CENARIO_COLS, '')
        item['cenario_id'] = key
        item['modalidade'] = mod
        item['observacoes'] = 'Preencher parametros e suas fontes antes de calcular lucro; não preencher desconhecido com zero.'
        values.append(item)
    _write(path, pd.DataFrame(values, columns=CENARIO_COLS))


def _extrair_ancoras(raiz: Path, out: Path) -> None:
    _write(out / 'catalogo_variaveis.csv', pd.DataFrame(VARIAVEIS, columns=[
        'variavel','dominio','metodo','valor_referencia','unidade','granularidade','fonte_id','status']))
    _write(out / 'fontes_pesquisa.csv', pd.DataFrame(REFERENCIAS, columns=[
        'fonte_id','instituicao','variavel','periodo','abrangencia','valor_referencia',
        'unidade','classe','url','limites']))


def _calcular(item: pd.Series, valid_ids: set[str], offers: pd.DataFrame) -> dict:
    result = {'cenario_id': str(item['cenario_id']), 'modalidade': str(item['modalidade']),
              'status': 'pendente', 'custos_mensais_parciais_brl': None,
              'receita_mensal_brl': None, 'custo_total_mensal_brl': None,
              'resultado_liquido_estimado_brl': None, 'custo_por_km_brl': None,
              'lacunas': '', 'componentes_conhecidos': '', 'oferta_conferida': ''}
    missing = []
    breakdown = {}
    modality = result['modalidade']
    if modality not in ('proprio_combustao','proprio_eletrico','alugado'):
        raise ValueError(f'Cenário {result["cenario_id"]}: modalidade inválida')
    def get(col):
        return _number(item[col])
    def need(col):
        n = get(col)
        if n is None:
            missing.append(col)
        return n
    km = need('km_mes')
    hrs = need('horas_online_mes')
    rec = need('receita_brl_por_hora_online')
    if hrs is not None and hrs <= 0:
        raise ValueError('horas_online_mes precisa ser > 0')
    if km is not None and km <= 0:
        raise ValueError('km_mes precisa ser > 0')
    if hrs is not None and rec is not None:
        result['receita_mensal_brl'] = round(hrs * rec, 2)
    veiculo_id = str(item['veiculo_id_inmetro']).strip() if pd.notna(item['veiculo_id_inmetro']) else ''
    if modality.startswith('proprio') and not veiculo_id:
        missing.append('veiculo_id_inmetro')
    if veiculo_id and veiculo_id not in valid_ids:
        raise ValueError(f'Cenário {result["cenario_id"]}: veiculo_id_inmetro inválido: {veiculo_id}')
    if modality.startswith('proprio'):
        breakdown['licenciamento'] = round(174.08/12, 2)
        ipva = need('ipva_brl_ano_confirmado')
        if ipva is not None: breakdown['ipva'] = ipva/12
        seguro = need('seguro_brl_ano')
        if seguro is not None: breakdown['seguro'] = seguro/12
        depreciacao = need('depreciacao_brl_mes')
        if depreciacao is not None: breakdown['depreciacao'] = depreciacao
        manutencao = need('manutencao_brl_km')
        if km is not None and manutencao is not None: breakdown['manutencao'] = km*manutencao
        jogo_pneus = need('jogo_pneus_brl')
        duracao = need('durabilidade_pneus_km')
        if duracao == 0:
            raise ValueError('durabilidade_pneus_km não pode ser zero')
        if km is not None and jogo_pneus is not None and duracao is not None:
            breakdown['pneus'] = jogo_pneus*km/duracao
    else:
        offer_id = str(item['oferta_uber_id']).strip() if pd.notna(item['oferta_uber_id']) else ''
        if not offer_id:
            missing.append('oferta_uber_id')
        else:
            selection = offers.loc[offers['id_publico_oferta'].astype('string').eq(offer_id)]
            if len(selection) != 1:
                raise ValueError(f'Oferta Uber inexistente/duplicada: {offer_id}')
            offer = selection.iloc[0]
            apt = _boolean(offer['apto_modelo_economico'])
            if apt is not True:
                raise ValueError(f'Oferta não aprovada economicamente: {offer_id}')
            rent = _number(offer['valor_mensal_equivalente'])
            if rent is None: missing.append('valor_mensal_equivalente_oferta')
            else: breakdown['aluguel'] = rent
            result['oferta_conferida'] = offer_id
            # Inclusion fields not reliable enough to silently skip costs.
            for category, field, parameter, annual in [
                ('seguro','seguro_incluso','seguro_brl_ano',True),
                ('manutencao','manutencao_inclusa','manutencao_brl_km',False),
                ('ipva','ipva_incluso','ipva_brl_ano_confirmado',True),
            ]:
                claimed = _boolean(offer[field])
                contract = _boolean(item[f'{category}_incluido_contrato'])
                if contract is True:
                    if claimed is not True:
                        missing.append(f'confirmar_inclusao_{category}_no_contrato')
                    continue
                if contract is None:
                    missing.append(f'{category}_incluido_contrato')
                    continue
                value = need(parameter)
                if value is not None and km is not None:
                    breakdown[category] = value/12 if annual else value*km
        included_lic = _boolean(item['licenciamento_incluido_contrato'])
        if included_lic is False: breakdown['licenciamento'] = 174.08/12
        elif included_lic is None: missing.append('licenciamento_incluido_contrato')
        dep = get('depreciacao_brl_mes')
        if dep is not None:
            raise ValueError('Não adicionar depreciação do carro locado no custo do motorista; já está no aluguel')
    if modality == 'proprio_combustao':
        fuel = need('preco_combustivel_brl_l')
        eff = need('eficiencia_combustivel_km_l')
        if eff == 0: raise ValueError('eficiencia_combustivel_km_l precisa ser >0')
        if km is not None and fuel is not None and eff is not None: breakdown['combustivel'] = km*fuel/eff
    else:
        # Electric scenario only when supplied; rented fuel-only option may need a distinct scenario.
        if modality == 'proprio_eletrico':
            rate = need('preco_energia_brl_kwh')
            consumption = need('consumo_eletrico_kwh_km')
            loss = get('perda_recarga_pct')
            if loss is None: missing.append('perda_recarga_pct (usar 0 somente se justificadamente desprezada)')
            elif loss >= 100: raise ValueError('perda_recarga_pct deve ser < 100')
            if km is not None and rate is not None and consumption is not None and loss is not None:
                breakdown['energia'] = km*rate*consumption/(1-loss/100)
        elif modality == 'alugado':
            # Existing offers can be ICE, hybrid or EV. Require explicit energy cost without assuming powertrain.
            fuel = get('preco_combustivel_brl_l')
            eff = get('eficiencia_combustivel_km_l')
            rate = get('preco_energia_brl_kwh')
            consumption = get('consumo_eletrico_kwh_km')
            if fuel is not None and eff is not None and rate is None and consumption is None:
                if eff <= 0: raise ValueError('eficiência precisa ser >0')
                if km is not None: breakdown['combustivel'] = km*fuel/eff
            elif rate is not None and consumption is not None and fuel is None and eff is None:
                loss = get('perda_recarga_pct')
                if loss is None: missing.append('perda_recarga_pct')
                elif loss >= 100: raise ValueError('perda_recarga_pct precisa ser < 100')
                elif km is not None: breakdown['energia'] = km*rate*consumption/(1-loss/100)
            else:
                missing.append('energia_alugado: preencher par combustivel ou par eletrico, nao ambos')
    if not str(item['fonte_parametros']).strip():
        missing.append('fonte_parametros')
    others = need('outros_custos_brl_mes')
    if others is not None: breakdown['outros'] = others
    if breakdown:
        result['custos_mensais_parciais_brl'] = round(sum(breakdown.values()),2)
        result['componentes_conhecidos'] = '; '.join(f'{key}={value:.2f}' for key,value in breakdown.items())
    missing = list(dict.fromkeys(missing))
    result['lacunas'] = '; '.join(missing)
    if not missing:
        total = round(sum(breakdown.values()),2)
        result['status'] = 'calculado_condicional_parametros_declarados'
        result['custo_total_mensal_brl'] = total
        result['resultado_liquido_estimado_brl'] = round(result['receita_mensal_brl']-total,2)
        result['custo_por_km_brl'] = round(total/km,4)
    return result


def executar(raiz: Path) -> None:
    out = raiz / 'dados_complementares' / 'etapa19'
    out.mkdir(parents=True, exist_ok=True)
    _extrair_ancoras(raiz, out)
    scenario = out / 'parametros_cenarios.csv'
    quotes = out / 'cotacoes.csv'
    _template_cenarios(scenario)
    if not quotes.exists():
        _write(quotes, pd.DataFrame(columns=COTACOES_COLS))
    folder, master_version = _localizar_mestre(raiz)
    vehicles = _veiculos(folder)
    offers = _ofertas(folder)
    _write(out / 'referencia_veiculos_inmetro.csv', vehicles)
    _write(out / 'ofertas_uber_para_cenario.csv', offers)
    quotes_data = pd.read_csv(quotes, dtype='string', keep_default_na=False)
    missing_quote = set(COTACOES_COLS)-set(quotes_data.columns)
    if missing_quote:
        raise ValueError(f'Arquivo de cotacoes sem colunas: {sorted(missing_quote)}')
    if len(quotes_data):
        for idx, quote in quotes_data.iterrows():
            if not str(quote['url_fonte']).strip() or not str(quote['data_referencia']).strip():
                raise ValueError(f'Cotação linha {idx+2}: fonte URL e data obrigatórias')
            if _number(quote['valor_brl']) is None:
                raise ValueError(f'Cotação linha {idx+2}: valor vazio')
    params = pd.read_csv(scenario, dtype='string', keep_default_na=False)
    missing = set(CENARIO_COLS)-set(params.columns)
    if missing:
        raise ValueError(f'Parâmetros sem colunas obrigatórias: {sorted(missing)}')
    if params['cenario_id'].isna().any() or params['cenario_id'].duplicated().any() or params['cenario_id'].eq('').any():
        raise ValueError('cenario_id deve existir e ser único')
    ids = set(vehicles['veiculo_id_inmetro'])
    results = [_calcular(row, ids, offers) for _,row in params.iterrows()]
    calc = pd.DataFrame(results)
    _write(out / 'resultados_cenarios.csv', calc)
    gaps = []
    for row in results:
        for gap in str(row['lacunas']).split('; '):
            if gap:
                gaps.append({'cenario_id':row['cenario_id'],'campo_ou_condicao':gap,'status':'pendente','acao':'obter evidência e preencher parametros_cenarios.csv'})
    _write(out / 'lacunas_cenarios.csv', pd.DataFrame(gaps,columns=['cenario_id','campo_ou_condicao','status','acao']))
    manifest = {'gerado_em_utc':datetime.now(timezone.utc).isoformat(),
                'versao_mestre_utilizada':master_version,
                'tabelas_mestres_localizadas':folder is not None,
                'qtd_veiculos_referencia':len(vehicles),'qtd_ofertas':len(offers),
                'qtd_cenarios':len(results),'qtd_cenarios_completos':int(calc['status'].ne('pendente').sum()),
                'entradas':{'parametros_cenarios.csv':_sha256(scenario),'cotacoes.csv':_sha256(quotes)},
                'licenciamento_anual_oficial_brl':174.08,
                'alertas':['Não substituir dados ausentes por zero.','Valores pesquisa Cebrap são benchmark, não receita líquida do cenário.',
                           'Não inserir isenção IPVA sem comprovante.','Não somar seguro/manutenção/IPVA incluídos em locação.']}
    (out/'manifesto.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    info = f'''# PI06 — Relatório etapa 1.9\n\nGerado: {manifest['gerado_em_utc']}\n\n- Versão de mestres: {master_version or 'não encontrada'}\n- Veículos disponíveis: {len(vehicles)}\n- Ofertas Uber: {len(offers)}\n- Cenários avaliados: {len(results)}\n- Cenários matematicamente completos: {manifest['qtd_cenarios_completos']}\n- Lacunas de parâmetros: {len(gaps)}\n\n## Status\nA etapa 1.9 fica **estruturada** com fontes e parâmetros. Cenários sem preenchimento não têm lucro calculado.\n\n## Prioridades\n1. Usar `dados_complementares/ipva_sp_2026/` como referência tributária; confirmar vínculo do veículo antes de preencher o IPVA anual.\n2. Cotar seguro com uso profissional em São Paulo, marcando perfil, período e cobertura.\n3. Registrar plano de revisão por km e valores de pneus por dimensão/vida útil; não adotar custo único universal.\n4. Capturar tarifa residencial efetiva e/ou tarifa do operador público com data, impostos e cobrança por tempo.\n5. Definir remuneração BRL/hora **online**, incluindo períodos sem corrida; não transplantar BRL/hora em corrida.\n6. Depreciação exige série histórica comparável do mesmo veículo; FIPE novembro/2026 isolada não fornece taxa anual.\n7. Para contrato Uber, marcar explicitamente itens incluídos e não incluídos após leitura da oferta/contrato.\n\n## Fórmulas\n- Licenciamento proprietário: 174,08 / 12.\n- Seguro, IPVA: valor anual / 12.\n- Pneus: jogo de pneus BRL × km/mês / vida útil km.\n- Manutenção: BRL/km × km/mês.\n- Gasolina: km/mês × R$/litro / km/l.\n- Elétrico: km/mês × kWh/km × R$/kWh / (1 − perda_recarga_pct/100).\n- Receita: horas **online**/mês × BRL/hora online.\n- Resultado líquido **estimado**: receita informada − custos, apenas quando todos os parâmetros obrigatórios estiverem disponíveis.\n\n## Limitações\nEstudo Cebrap/Amobitec cobre dados de 2024 e apresenta rendimento líquido mensal para 40 h/semana, não equivalente à receita bruta em hora online; custo do motorista não deve ser confundido com tarifa cobrada ao passageiro. Atualizar valores periodicamente.\n'''
    (out/'RELATORIO_ETAPA19.md').write_text(info,encoding='utf-8')
    print(f'[OK] Licenciamento oficial 2026: R$ 174,08/ano')
    print(f'[OK] Tabelas mestre: {len(vehicles)} veículos INMETRO, {len(offers)} ofertas Uber')
    print(f'[OK] Variáveis catalogadas: {len(VARIAVEIS)} | Fontes documentadas: {len(REFERENCIAS)}')
    print(f'[OK] Cenários: {len(results)} | completos: {manifest["qtd_cenarios_completos"]} | lacunas: {len(gaps)}')
    print(f'[OK] Entrega: {out}')
    print('Observação: pendências de preço e receita continuam declaradas, sem valores inventados.')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raiz', type=Path, default=Path(__file__).resolve().parent,
                        help='Raiz do projeto (default: pasta do script)')
    args = parser.parse_args()
    executar(args.raiz.expanduser().resolve())

if __name__ == '__main__':
    main()
