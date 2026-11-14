"""PI06: auditoria conservadora da fila de 122 candidatos unicos.
Nao homologa nenhuma correspondencia; cria evidencias para revisao humana.
"""
from pathlib import Path
import re
import unicodedata
import pandas as pd

PASTA = Path('dados_relatorios/integracao_veiculos')
ORIGEM = PASTA / 'revisao_inmetro_candidato_unico_v3.csv'
DESTINO = PASTA / 'revisao_inmetro_candidato_unico_auditada_v4.csv'


def normalizar(valor):
    if pd.isna(valor):
        return ''
    texto = unicodedata.normalize('NFKD', str(valor))
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', texto.upper().strip())


def avaliar(row):
    f = normalizar(row['combustivel_fipe'])
    i = normalizar(row['tipo_propulsao_inmetro'])
    mf = normalizar(row['modelo_fipe'])
    mi = normalizar(row['modelo_inmetro'])
    vi = normalizar(row['versao_inmetro'])
    avisos = []
    if ('ELETR' in f and 'ELETR' not in i):
        avisos.append('FIPE_ELETRICO_INMETRO_NAO_ELETRICO')
    if ('HIBRID' in f and 'HIBRID' not in i and 'PLUG' not in i):
        avisos.append('FIPE_HIBRIDO_INMETRO_COMBUSTAO_OU_OUTRO')
    if ('GASOLINA' in f or 'ALCOOL' in f or 'FLEX' in f) and i == 'ELETRICO':
        avisos.append('FIPE_COMBUSTIVEL_INMETRO_ELETRICO')
    # Semelhança de nome comercial nao comprova versao, motor ou ano.
    # Só sinaliza palavras distintivas para orientar revisão.
    marcas_edicao = ('CABRIOLET', 'CABRIO', 'COUPE', 'SPORTBACK', 'PERFORMANCE',
                     'AMBIENTE', 'ATTRACTION', 'PRESTIGE', 'S LINE', 'QUATTRO',
                     'TOURING', 'SEDAN', 'AVANT')
    diferencas = [x for x in marcas_edicao if (x in mf) != (x in (mi + ' ' + vi))]
    if diferencas:
        avisos.append('VERSAO_CARROCERIA_DIVERGENTE_OU_NAO_DEMONSTRADA')
    avisos.append('ANO_VERSAO_INMETRO_NAO_VERIFICADOS')
    return pd.Series({
        'alertas_v4': ';'.join(avisos),
        'indicadores_divergentes_v4': ';'.join(diferencas),
        'prioridade_v4': 'ALTA_CONTRADICAO_PROPULSAO' if any(
            x.startswith('FIPE_') for x in avisos
        ) else 'REVISAO_MANUAL_MODELO_VERSAO',
        'status_validacao_v4': 'PENDENTE',
        'revisao_humana_obrigatoria': True,
    })


def main():
    if not ORIGEM.is_file():
        raise FileNotFoundError(ORIGEM)
    if DESTINO.exists():
        raise FileExistsError(f'Saida existente, nao sobrescrever: {DESTINO}')
    df = pd.read_csv(ORIGEM, dtype=str, low_memory=False)
    obrigatorias = {'veiculo_id', 'modelo_fipe', 'combustivel_fipe',
                    'modelo_inmetro', 'versao_inmetro', 'tipo_propulsao_inmetro'}
    if not obrigatorias.issubset(df.columns):
        raise ValueError(f'Colunas ausentes: {sorted(obrigatorias-set(df.columns))}')
    if df.veiculo_id.isna().any() or df.veiculo_id.duplicated().any():
        raise ValueError('Chaves veiculo_id ausentes ou duplicadas')
    if 'decisao_match_inmetro' in df.columns and df['decisao_match_inmetro'].fillna('PENDENTE').ne('PENDENTE').any():
        raise ValueError('Há revisoes humanas anteriores; revisar antes de criar nova fila')
    aval = df.apply(avaliar, axis=1)
    saida = pd.concat([df, aval], axis=1)
    saida = saida.sort_values(['prioridade_v4','marca_fipe','modelo_fipe'], kind='stable')
    saida.to_csv(DESTINO, index=False, encoding='utf-8-sig')
    print('=== AUDITORIA CONSERVADORA V4 ===')
    print('Candidatos revisados:',len(saida))
    print(saida['prioridade_v4'].value_counts().to_string())
    print('Correspondencias aprovadas automaticamente: 0')
    print('Saida:',DESTINO)
    print('\nEXEMPLOS COM ALERTA DE PROPULSAO:')
    print(saida[saida['prioridade_v4'].eq('ALTA_CONTRADICAO_PROPULSAO')][
        ['marca_fipe','modelo_fipe','combustivel_fipe','modelo_inmetro','versao_inmetro','tipo_propulsao_inmetro']
    ].head(12).to_string(index=False))

if __name__ == '__main__':
    main()
