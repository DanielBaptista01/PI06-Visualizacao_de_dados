"""PI06: triagem conservadora de candidatos FIPE x Uber x INMETRO.

Nenhuma correspondencia e homologada; nenhum consumo e atribuido.
Requer arquivos criados por construir_tabela_mestra.py.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd


def executar(pasta: Path) -> dict:
    mestre = pd.read_csv(pasta / 'tabela_mestra_fipe_parcial.csv', dtype=str, low_memory=False)
    uber = pd.read_csv(pasta / 'candidatos_uber.csv', dtype=str, low_memory=False)
    inmetro = pd.read_csv(pasta / 'candidatos_inmetro.csv', dtype=str, low_memory=False)

    for nome, df in [('mestre', mestre), ('uber', uber), ('inmetro', inmetro)]:
        if 'veiculo_id' not in df.columns:
            raise ValueError(f'{nome}: coluna veiculo_id ausente')
    if mestre['veiculo_id'].isna().any() or mestre['veiculo_id'].duplicated().any():
        raise ValueError('Mestre com chaves ausentes ou repetidas')

    # As categorias sao possibilidades independentes; nao contar linhas como veiculos.
    uber_comp = uber.loc[uber['status'].eq('candidato_ano_compativel')].copy()
    n_uber = uber_comp.groupby('veiculo_id').size().rename('qtd_categorias_ano_compativel')
    n_inmetro = inmetro.groupby('veiculo_id').size().rename('qtd_versoes_inmetro_candidatas')

    # O mesmo veiculo pode ter candidatos INMETRO de tecnologias divergentes.
    n_prop = (inmetro.groupby('veiculo_id')['tipo_propulsao_inmetro']
              .nunique(dropna=True).rename('qtd_propulsoes_inmetro_candidatas'))

    resumo = mestre[['veiculo_id', 'marca_fipe', 'modelo_fipe', 'ano_modelo',
                     'combustivel_fipe', 'preco_fipe_rs']].copy()
    resumo = resumo.join(n_uber, on='veiculo_id').join(n_inmetro, on='veiculo_id').join(n_prop, on='veiculo_id')
    for c in ['qtd_categorias_ano_compativel', 'qtd_versoes_inmetro_candidatas',
              'qtd_propulsoes_inmetro_candidatas']:
        resumo[c] = resumo[c].fillna(0).astype(int)

    sem_ano = resumo['ano_modelo'].isna() | resumo['ano_modelo'].astype(str).str.strip().eq('')
    tem_uber = resumo['qtd_categorias_ano_compativel'].gt(0)
    tem_inmetro = resumo['qtd_versoes_inmetro_candidatas'].gt(0)
    unica = resumo['qtd_versoes_inmetro_candidatas'].eq(1)
    divergencia = resumo['qtd_propulsoes_inmetro_candidatas'].gt(1)

    # Ordem definida para categorias mutuamente exclusivas, sempre candidatas.
    resumo['fila_revisao'] = 'sem_ano_uber_compativel'
    resumo.loc[~sem_ano & ~tem_uber, 'fila_revisao'] = 'sem_categoria_uber_ano_compativel'
    resumo.loc[~sem_ano & tem_uber & ~tem_inmetro, 'fila_revisao'] = 'sem_inmetro_candidato'
    resumo.loc[~sem_ano & tem_uber & tem_inmetro, 'fila_revisao'] = 'revisar_versoes_ambiguas'
    resumo.loc[~sem_ano & tem_uber & tem_inmetro & unica, 'fila_revisao'] = 'revisar_candidato_unico'
    resumo.loc[~sem_ano & tem_uber & tem_inmetro & divergencia, 'fila_revisao'] = 'revisar_propulsao_divergente'

    resumo['consumo_homologado'] = False
    resumo['elegibilidade_uber_homologada'] = False
    resumo['apto_calculo_automatico'] = False

    # Contexto de categorias elegiveis apenas pela janela de ano, nao homologadas.
    categorias = (uber_comp.groupby('veiculo_id')['categoria_uber']
                  .agg(lambda s: ';'.join(sorted(set(s.dropna())))).rename('categorias_ano_compativel'))
    resumo = resumo.join(categorias, on='veiculo_id')

    ordem = {'revisar_candidato_unico': 0, 'revisar_versoes_ambiguas': 1,
             'revisar_propulsao_divergente': 2, 'sem_inmetro_candidato': 3,
             'sem_categoria_uber_ano_compativel': 4, 'sem_ano_uber_compativel': 5}
    resumo['_ordem'] = resumo['fila_revisao'].map(ordem)
    resumo = resumo.sort_values(['_ordem', 'marca_fipe', 'modelo_fipe', 'ano_modelo'], kind='stable').drop(columns='_ordem')

    destino = pasta / 'triagem_priorizada_v2.csv'
    if destino.exists():
        raise FileExistsError(f'Arquivo ja existe; preserve ou mova antes: {destino}')
    resumo.to_csv(destino, index=False, encoding='utf-8-sig')

    numeros = {
        'veiculos_fipe': len(resumo),
        'com_ano_compativel_em_alguma_categoria_uber': int(tem_uber.sum()),
        'com_candidato_inmetro': int(tem_inmetro.sum()),
        'com_ambos': int((tem_uber & tem_inmetro).sum()),
        'revisao_candidato_inmetro_unico_e_uber_ano': int((~sem_ano & tem_uber & unica).sum()),

    }
    # Substitui diagnostico anterior por contagem simples consistente.
    numeros['revisao_multiplas_versoes_inmetro_e_uber_ano'] = int(
        (resumo['fila_revisao'].isin(['revisar_versoes_ambiguas','revisar_propulsao_divergente'])).sum()
    )
    print('\n=== TRIAGEM DE MATCHES ===')
    for k, v in numeros.items():
        print(f'{k}: {v}')
    print('\nFILA DE REVISAO:')
    print(resumo['fila_revisao'].value_counts().to_string())
    print('\nArquivo:', destino)
    return numeros


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--pasta', type=Path, default=Path('dados_relatorios/integracao_veiculos'))
    executar(parser.parse_args().pasta)
