"""PI06: motor econômico mínimo, sem matching automático de veículos.

Requer apenas Python 3.10+. Valores de consumo e custos externos são cenários
explícitos; a ausência de dados não é convertida em zero.
"""
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional


def decimal_br(valor: object) -> Decimal:
    """Aceita 0.789, 0,789, R$ 1.234,56; rejeita campos vazios."""
    if valor is None or str(valor).strip().lower() in ('', 'nan', 'none', 'null'):
        raise ValueError('Valor numerico obrigatorio ausente')
    s = str(valor).strip().replace('R$', '').replace('\u00a0', '').replace(' ', '')
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.')
    try:
        return Decimal(s)
    except InvalidOperation as exc:
        raise ValueError(f'Numero invalido: {valor!r}') from exc


def _nao_negativo(nome: str, valor: Optional[Decimal]) -> None:
    if valor is not None and valor < 0:
        raise ValueError(f'{nome} deve ser >= 0')


def _positivo(nome: str, valor: Decimal) -> None:
    if valor <= 0:
        raise ValueError(f'{nome} deve ser > 0')


def obter_precos(raiz: Path) -> dict[str, object]:
    """Lê snapshots existentes da ANP (capital) e ANEEL (cenário residencial)."""
    anp = raiz / 'dados_limpos' / '03_ANP_PRECOS_CAPITAL_NOV2026.csv'
    aneel = raiz / 'dados_limpos' / '02_ANEEL_CENARIO_ENERGIA_SP.csv'
    with anp.open('r', encoding='utf-8-sig', newline='') as f:
        linhas = list(csv.DictReader(f))
    produtos = {}
    for r in linhas:
        if r.get('municipio', '').strip().upper() != 'SAO PAULO':
            continue
        p = r['produto'].strip().upper()
        if p in ('GASOLINA COMUM', 'ETANOL'):
            if p in produtos:
                raise ValueError(f'ANP: produto duplicado na capital: {p}')
            produtos[p] = r
    if set(produtos) != {'GASOLINA COMUM', 'ETANOL'}:
        raise ValueError('ANP: faltam gasolina comum ou etanol para Sao Paulo')
    periodos = {(r['periodo_inicio'], r['periodo_fim']) for r in produtos.values()}
    if len(periodos) != 1:
        raise ValueError('ANP: periodos distintos entre os combustiveis')
    with aneel.open('r', encoding='utf-8-sig', newline='') as f:
        linhas_aneel = list(csv.DictReader(f))
    if len(linhas_aneel) != 1:
        raise ValueError('ANEEL: esperado um unico cenario tarifario')
    e = linhas_aneel[0]
    if e['distribuidora'].strip().upper() != 'ENEL SP':
        raise ValueError('ANEEL: distribuidora nao corresponde a Enel SP')
    if e['mes_cenario'] != '2026-11':
        raise ValueError('ANEEL: cenario nao corresponde a novembro/2026')
    preco_eletrico = decimal_br(e['tarifa_com_bandeira_rs_kwh'])
    preco_gasolina = decimal_br(produtos['GASOLINA COMUM']['preco_medio_rs_litro'])
    preco_etanol = decimal_br(produtos['ETANOL']['preco_medio_rs_litro'])
    for nome, p in [('gasolina', preco_gasolina), ('etanol', preco_etanol), ('eletricidade', preco_eletrico)]:
        _positivo(f'preco {nome}', p)
    return {
        'gasolina_rs_l': preco_gasolina,
        'etanol_rs_l': preco_etanol,
        'eletricidade_rs_kwh': preco_eletrico,
        'anp_periodo': next(iter(periodos)),
        'aneel_mes': e['mes_cenario'],
        'aneel_inclui_tributos': e['inclui_tributos'].strip().lower() == 'true',
        'anp_origem': str(anp),
        'aneel_origem': str(aneel),
    }


@dataclass(frozen=True)
class Cenario:
    identificador: str
    tecnologia: str  # gasolina, etanol, hibrido, eletrico, plugin
    km_total_mes: Decimal
    consumo_combustivel_km_l: Optional[Decimal] = None
    combustivel: Optional[str] = None  # gasolina ou etanol no hibrido/plugin
    consumo_eletrico_kwh_km: Optional[Decimal] = None
    eficiencia_recarga: Optional[Decimal] = None  # (0,1], se eletrico/plugin
    fracao_km_eletrico: Optional[Decimal] = None  # [0,1], se plugin
    custo_variavel_extra_rs_km: Optional[Decimal] = None
    custo_fixo_rs_mes: Optional[Decimal] = None
    depreciacao_rs_mes: Optional[Decimal] = None
    receita_motorista_rs_mes: Optional[Decimal] = None  # ja liquida de taxas da plataforma
    horas_trabalhadas_mes: Optional[Decimal] = None


def calcular(c: Cenario, precos: dict[str, object]) -> dict[str, object]:
    t = c.tecnologia.strip().lower()
    if t not in {'gasolina', 'etanol', 'hibrido', 'eletrico', 'plugin'}:
        raise ValueError(f'Tecnologia desconhecida: {c.tecnologia}')
    _positivo('km_total_mes', c.km_total_mes)
    _nao_negativo('custo_variavel_extra_rs_km', c.custo_variavel_extra_rs_km)
    _nao_negativo('custo_fixo_rs_mes', c.custo_fixo_rs_mes)
    _nao_negativo('depreciacao_rs_mes', c.depreciacao_rs_mes)
    _nao_negativo('receita_motorista_rs_mes', c.receita_motorista_rs_mes)
    if c.horas_trabalhadas_mes is not None:
        _positivo('horas_trabalhadas_mes', c.horas_trabalhadas_mes)

    fuel_per_km = Decimal('0')
    elet_per_km = Decimal('0')
    eletrico_f = Decimal('1') if t == 'eletrico' else Decimal('0')
    if t == 'plugin':
        if c.fracao_km_eletrico is None or not (0 <= c.fracao_km_eletrico <= 1):
            raise ValueError('Plugin exige fracao_km_eletrico entre 0 e 1')
        eletrico_f = c.fracao_km_eletrico

    if t in ('gasolina', 'etanol', 'hibrido', 'plugin'):
        if c.consumo_combustivel_km_l is None:
            raise ValueError('Consumo combustivel km/l obrigatorio')
        _positivo('consumo_combustivel_km_l', c.consumo_combustivel_km_l)
        fuel = t if t in ('gasolina', 'etanol') else (c.combustivel or '').lower()
        if fuel not in ('gasolina', 'etanol'):
            raise ValueError('Hibrido/plugin exige combustivel gasolina ou etanol')
        fuel_per_km = (Decimal('1') - eletrico_f) * precos[f'{fuel}_rs_l'] / c.consumo_combustivel_km_l

    if t in ('eletrico', 'plugin'):
        if c.consumo_eletrico_kwh_km is None or c.eficiencia_recarga is None:
            raise ValueError('Eletrico/plugin exige consumo kWh/km e eficiencia de recarga')
        _positivo('consumo_eletrico_kwh_km', c.consumo_eletrico_kwh_km)
        if not (0 < c.eficiencia_recarga <= 1):
            raise ValueError('eficiencia_recarga deve estar em (0,1]')
        elet_per_km = (eletrico_f * c.consumo_eletrico_kwh_km
                       * precos['eletricidade_rs_kwh'] / c.eficiencia_recarga)

    energia_km = fuel_per_km + elet_per_km
    energia_mes = energia_km * c.km_total_mes
    extra = c.custo_variavel_extra_rs_km
    fixo = c.custo_fixo_rs_mes
    depr = c.depreciacao_rs_mes
    completo = all(x is not None for x in (extra, fixo, depr))
    total_mes = (energia_mes + extra * c.km_total_mes + fixo + depr) if completo else None
    custo_total_km = total_mes / c.km_total_mes if completo else None
    lucro = c.receita_motorista_rs_mes - total_mes if completo and c.receita_motorista_rs_mes is not None else None
    ponto_eq = custo_total_km if completo else None
    ponto_eq_hora = total_mes / c.horas_trabalhadas_mes if completo and c.horas_trabalhadas_mes is not None else None
    return {
        'identificador': c.identificador, 'tecnologia': t,
        'km_total_mes': c.km_total_mes,
        'custo_combustivel_rs_km': fuel_per_km,
        'custo_eletrico_rs_km': elet_per_km,
        'custo_energetico_rs_km': energia_km,
        'custo_energetico_rs_mes': energia_mes,
        'custo_total_rs_mes': total_mes,
        'custo_total_rs_km': custo_total_km,
        'ponto_equilibrio_rs_km': ponto_eq,
        'ponto_equilibrio_rs_hora': ponto_eq_hora,
        'resultado_liquido_estimado_rs_mes': lucro,
        'custos_complementares_completos': completo,
        'receita_informada': c.receita_motorista_rs_mes is not None,
        'nota': ('Cenario com parametros de custo completos' if completo else
                 'Somente custo energetico: custos complementares faltantes'),
    }


def exemplo(raiz: Path) -> dict[str, object]:
    precos = obter_precos(raiz)
    # Hipoteses ilustrativas, NAO sao consumos reais de um modelo INMETRO.
    km = Decimal('3000')
    cenarios = [
        Cenario('EXEMPLO_GASOLINA', 'gasolina', km, consumo_combustivel_km_l=Decimal('12')),
        Cenario('EXEMPLO_ETANOL', 'etanol', km, consumo_combustivel_km_l=Decimal('8')),
        Cenario('EXEMPLO_HIBRIDO', 'hibrido', km, combustivel='gasolina', consumo_combustivel_km_l=Decimal('18')),
        Cenario('EXEMPLO_ELETRICO', 'eletrico', km, consumo_eletrico_kwh_km=Decimal('0.15'), eficiencia_recarga=Decimal('0.90')),
        Cenario('EXEMPLO_PLUGIN', 'plugin', km, combustivel='gasolina', consumo_combustivel_km_l=Decimal('15'),
                consumo_eletrico_kwh_km=Decimal('0.17'), eficiencia_recarga=Decimal('0.90'), fracao_km_eletrico=Decimal('0.60')),
    ]
    return {'fontes_precos': precos, 'hipoteses': 'Consumos e km ilustrativos; custos extras/receita nao informados',
            'resultados': [calcular(c, precos) for c in cenarios]}


def _json_default(x):
    if isinstance(x, Decimal):
        return float(x)
    if isinstance(x, Path):
        return str(x)
    raise TypeError(type(x).__name__)


def main():
    parser = argparse.ArgumentParser(description='PI06 - Modelo economico minimo')
    parser.add_argument('--raiz', type=Path, default=Path('.'), help='Raiz do repositorio PI06')
    parser.add_argument('--demo', action='store_true', help='Executa cenarios ilustrativos sem receita')
    parser.add_argument('--saida', type=Path, default=None, help='Caminho opcional para salvar JSON')
    args = parser.parse_args()
    if not args.demo:
        parser.error('Nesta primeira versao, use --demo; integracao de CSV de veiculos sera proxima etapa.')
    res = exemplo(args.raiz)
    texto = json.dumps(res, ensure_ascii=False, indent=2, default=_json_default)
    print(texto)
    if args.saida:
        if args.saida.exists():
            raise FileExistsError(f'Arquivo ja existe: {args.saida}')
        args.saida.parent.mkdir(parents=True, exist_ok=True)
        args.saida.write_text(texto + '\n', encoding='utf-8')
        print(f'Arquivo salvo: {args.saida}')


if __name__ == '__main__':
    main()
