"""PI06: auditoria única Uber SP 2026 -> candidatos FIPE -> fila técnica.

Não aprova veículos por inferência. Não consulta APIs nem altera arquivos brutos.
Depois de validar características documentadas, libera SOMENTE consultas de anos
FIPE para versões, não a elegibilidade final de um veículo individual.

Fontes das regras (consultadas em 2026-11-06):
- https://www.uber.com/br/pt-br/drive/requirements/?city=sao-paulo
- https://www.uber.com/br/pt-br/blog/mudancas-nas-categorias-black-e-comfort-a-partir-de-janeiro-2026/
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from datetime import date
from pathlib import Path

import pandas as pd

CATEGORIAS = ('uberx', 'comfort', 'black', 'electric')
FONTE = 'https://www.uber.com/br/pt-br/blog/mudancas-nas-categorias-black-e-comfort-a-partir-de-janeiro-2026/'
REGRAS = 'https://www.uber.com/br/pt-br/drive/requirements/?city=sao-paulo'
COMFORT_EXCECOES = {'ETIOS SEDAN': 2019, 'VOYAGE': 2019, 'PRISMA': 2019,
                    'LOGAN': 2019, 'COBALT': 2019, 'ARGO': 2023, 'POLO': 2023}
BLACK_EXCECOES = {'VIRTUS': 2025, 'DUSTER': 2023, 'NIVUS': 2023, 'CITY': 2023}
BLACK_EXCLUIDOS = {
    ('RENAULT', 'KARDIAN'), ('CHERY', 'TIGGO 3X'),
    ('PEUGEOT', 'E 2008'), ('CHERY', 'TIGGO 3'),
    ('HYUNDAI', 'KONA HYBRID'), ('JAC MOTORS', 'J3 TURIN'),
    ('JAC MOTORS', 'IEV 40'),
}
COLUNAS_EVIDENCIA = ['brand_id', 'model_id', 'categoria_uber', 'portas', 'lugares',
                     'ar_condicionado', 'tecnologia', 'carroceria',
                     'modelo_uber_confirmado', 'lista_oficial_sp_confirmada',
                     'fonte_url', 'data_verificacao']


def normalizar(valor: object) -> str:
    """Normaliza nomes preservando a distinção entre um modelo e sua versão PLUS."""
    if pd.isna(valor):
        return ''
    texto = unicodedata.normalize('NFKD', str(valor).replace('+', ' PLUS ').strip())
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', re.sub(r'[^A-Z0-9]+', ' ', texto.upper())).strip()


def chave_marca(marca: object) -> str:
    return normalizar(re.sub(r'\s*Down\s*$', '', str(marca), flags=re.I))


def ano_regra(marca: str, modelo: str, categoria: str, ano_fonte: object, referencia: date) -> tuple[object, str, str]:
    """Aplica somente limites conhecidos; sem comprovação técnica não aprova."""
    if pd.isna(ano_fonte):
        return pd.NA, 'nao_listado', 'Categoria ausente do snapshot; confirmar lista oficial atual'
    m, b = normalizar(modelo), chave_marca(marca)
    if categoria == 'uberx':
        ano = max(int(ano_fonte), referencia.year - 10)
    elif categoria == 'comfort':
        ano = max(int(ano_fonte), COMFORT_EXCECOES.get(m, 2018))
    elif categoria == 'black':
        ano = max(int(ano_fonte), BLACK_EXCECOES.get(m, 2019))
    else:
        # A lista Electric demanda confirmação específica; não assumir regra UberX.
        ano = int(ano_fonte)
    if categoria == 'comfort' and (b, m) == ('RENAULT', 'LOGAN') and referencia >= date(2026, 7, 6):
        return ano, 'bloqueado', 'Renault Logan excluído do Comfort desde 06/07/2026'
    if categoria == 'black' and (b, m) in BLACK_EXCLUIDOS and referencia >= date(2026, 1, 5):
        return ano, 'bloqueado', 'Modelo excluído do Black desde 05/01/2026'
    return ano, 'pendente', 'Faltam comprovação da versão e características físicas'


def expandir_mapeamento(mapa: pd.DataFrame) -> pd.DataFrame:
    """Explode lista JSON FIPE; não seleciona versões de forma arbitrária."""
    obrigatorias = {'marca_uber', 'modelo_uber', 'brand_id', 'status', 'candidatos_modelos'}
    faltando = obrigatorias - set(mapa.columns)
    if faltando:
        raise ValueError(f'Mapeamento sem colunas: {sorted(faltando)}')
    registros = []
    for i, row in mapa.iterrows():
        if row['status'] not in {'revisao_prefixo_unico', 'revisao_modelo_ambiguo', 'mapeado'}:
            continue
        if row['status'] == 'mapeado':
            if pd.isna(row.get('brand_id')) or pd.isna(row.get('model_id')) or pd.isna(row.get('modelo_fipe_match')):
                raise ValueError(f'Mapeado sem identificadores completos na linha {i}')
            registros.append({
                'marca_uber': row['marca_uber'], 'modelo_uber': row['modelo_uber'],
                'brand_id': str(row['brand_id']).removesuffix('.0'),
                'model_id': str(row['model_id']).removesuffix('.0'),
                'modelo_fipe': str(row['modelo_fipe_match']), 'status_match': 'mapeado',
            })
            continue
        if pd.isna(row['candidatos_modelos']) or pd.isna(row['brand_id']):
            raise ValueError(f'Candidatos ou marca FIPE ausente na linha {i}')
        try:
            candidatos = json.loads(row['candidatos_modelos'])
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError(f'JSON de candidatos inválido na linha {i}') from exc
        if not isinstance(candidatos, list) or not candidatos:
            raise ValueError(f'Lista de candidatos vazia/inválida na linha {i}')
        for candidato in candidatos:
            if not candidato.get('code') or not candidato.get('name'):
                raise ValueError(f'Candidato incompleto na linha {i}')
            registros.append({
                'marca_uber': row['marca_uber'], 'modelo_uber': row['modelo_uber'],
                'brand_id': str(row['brand_id']).removesuffix('.0'),
                'model_id': str(candidato['code']), 'modelo_fipe': str(candidato['name']),
                'status_match': row['status'],
            })
    candidatos_df = pd.DataFrame(registros)
    if candidatos_df.empty:
        raise ValueError('Nenhuma versão FIPE candidata no mapeamento')
    chaves = ['marca_uber', 'modelo_uber', 'brand_id', 'model_id']
    if candidatos_df.duplicated(chaves).any():
        raise ValueError('Duplicidade de correspondência Uber–FIPE')
    return candidatos_df


def regras_uber(uber: pd.DataFrame, referencia: date) -> pd.DataFrame:
    obrigatorias = {'marca', 'modelo'} | {f'{c}_ano_min' for c in CATEGORIAS}
    faltando = obrigatorias - set(uber.columns)
    if faltando:
        raise ValueError(f'Uber sem colunas: {sorted(faltando)}')
    if referencia.year != 2026:
        raise ValueError('Regras de 2026; atualizar fontes antes de usar em outro ano')
    dados = uber.copy()
    dados['marca_chave'] = dados['marca'].map(chave_marca)
    dados['modelo_chave'] = dados['modelo'].map(normalizar)
    if dados.duplicated(['marca_chave', 'modelo_chave']).any():
        raise ValueError('Marcas/modelos Uber duplicados após normalização')
    registros = []
    for row in dados.to_dict('records'):
        for cat in CATEGORIAS:
            valor = pd.to_numeric(pd.Series([row[f'{cat}_ano_min']]), errors='coerce').iloc[0]
            limite, status, motivo = ano_regra(row['marca'], row['modelo'], cat, valor, referencia)
            registros.append({
                'marca_uber': row['marca'], 'modelo_uber': row['modelo'],
                'marca_chave': row['marca_chave'], 'modelo_chave': row['modelo_chave'],
                'categoria_uber': cat, 'ano_min_fonte': valor,
                'ano_min_fabricacao_regra': limite, 'status_categoria': status,
                'motivo': motivo, 'fonte_regra': REGRAS if cat == 'uberx' else FONTE,
                'data_referencia': referencia.isoformat(),
            })
    return pd.DataFrame(registros)


def _ler_evidencias(path: Path) -> pd.DataFrame:
    """Evidência opcional por versão FIPE. Não infere atributos faltantes."""
    if not path.exists():
        return pd.DataFrame(columns=COLUNAS_EVIDENCIA)
    evid = pd.read_csv(path, dtype={'brand_id': 'string', 'model_id': 'string'})
    faltando = set(COLUNAS_EVIDENCIA) - set(evid.columns)
    if faltando:
        raise ValueError(f'Evidências sem colunas: {sorted(faltando)}')
    if evid.duplicated(['brand_id', 'model_id', 'categoria_uber']).any():
        raise ValueError('Evidências duplicadas por versão FIPE e categoria')
    return evid[COLUNAS_EVIDENCIA].copy()


def _sim(valor: object) -> bool:
    return not pd.isna(valor) and normalizar(valor) in {'SIM', 'TRUE', '1'}


def _evidencia_valida(row: pd.Series) -> bool:
    # Só admite evidência verificável, com referência e data explícitas.
    return (not pd.isna(row.get('fonte_url')) and
            str(row.get('fonte_url')).startswith(('https://', 'http://')) and
            not pd.isna(row.get('data_verificacao')) and
            bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(row.get('data_verificacao')))))


def _classificar(row: pd.Series) -> tuple[str, str]:
    if row['status_categoria'] == 'bloqueado':
        return 'bloqueado_regra', 'Exclusão oficial da categoria'
    if row['status_categoria'] == 'nao_listado':
        return 'fora_fila_categoria', 'Categoria não indicada na fonte'
    if not _evidencia_valida(row):
        return 'pendente_comprovacao', 'Sem documentação rastreável da versão'
    if not _sim(row.get('modelo_uber_confirmado')) or not _sim(row.get('lista_oficial_sp_confirmada')):
        return 'pendente_vinculo_oficial', 'Falta vínculo versão–modelo e confirmação da categoria na lista oficial SP'
    portas = pd.to_numeric(row.get('portas'), errors='coerce')
    lugares = pd.to_numeric(row.get('lugares'), errors='coerce')
    if pd.notna(portas) and portas < 4:
        return 'incompativel_portas', 'Menos de quatro portas comprovadas'
    if pd.notna(lugares) and lugares < 5:
        return 'incompativel_lugares', 'Capacidade abaixo de cinco lugares comprovada'
    if not pd.isna(row.get('ar_condicionado')) and not _sim(row['ar_condicionado']):
        return 'incompativel_ar', 'Sem ar-condicionado comprovado'
    if pd.isna(portas) or pd.isna(lugares) or pd.isna(row.get('ar_condicionado')):
        return 'pendente_comprovacao', 'Especificações físicas incompletas'
    if row['categoria_uber'] == 'electric':
        if pd.isna(row.get('tecnologia')):
            return 'pendente_tecnologia', 'Propulsão elétrica ainda não comprovada'
        if normalizar(row['tecnologia']) not in {'BEV', 'ELETRICO PURO'}:
            return 'incompativel_tecnologia', 'Propulsão não comprovada como elétrica pura'
    return 'apto_consultar_anos_fipe', 'Atributos básicos documentados; ano de fabricação e elegibilidade final ainda pendentes'


def validar_identidade_versoes(todas: pd.DataFrame) -> pd.DataFrame:
    """Detecta quando uma versão FIPE pertence a outra família Uber.

    Preserva todos os candidatos e registra os conflitos.
    Não comprova elegibilidade física nem aprova preços.
    """
    obrigatorias = {
        "marca_uber",
        "modelo_uber",
        "modelo_fipe",
        "brand_id",
        "model_id",
    }
    faltantes = obrigatorias - set(todas.columns)

    if faltantes:
        raise ValueError(
            f"Colunas ausentes: {sorted(faltantes)}"
        )

    dados = todas.copy()

    dados["marca_norm"] = dados["marca_uber"].map(chave_marca)
    dados["modelo_uber_norm"] = dados["modelo_uber"].map(normalizar)
    dados["modelo_fipe_norm"] = dados["modelo_fipe"].map(normalizar)

    familias = (
        dados[["marca_norm", "modelo_uber_norm"]]
        .drop_duplicates()
        .groupby("marca_norm")["modelo_uber_norm"]
        .agg(list)
        .to_dict()
    )

    def avaliar(linha: pd.Series) -> tuple[str, str]:
        uber = linha["modelo_uber_norm"]
        fipe = linha["modelo_fipe_norm"]

        if not uber or not fipe:
            return "revisar_identidade", "Nome ausente"

        if fipe != uber and not fipe.startswith(uber + " "):
            return (
                "revisar_identidade",
                "Nome FIPE não corresponde ao prefixo completo",
            )

        outros = [
            modelo
            for modelo in familias[linha["marca_norm"]]
            if modelo != uber
            and modelo.startswith(uber + " ")
            and (
                fipe == modelo
                or fipe.startswith(modelo + " ")
            )
        ]

        if outros:
            mais_especifico = max(outros, key=len)
            return (
                "conflito_familia",
                f"Possível correspondência com {mais_especifico}",
            )

        return (
            "candidato_coerente",
            "Nome compatível; exige demais validações",
        )

    chaves = [
        "marca_norm",
        "modelo_uber_norm",
        "modelo_fipe_norm",
    ]

    unicos = dados[chaves].drop_duplicates().copy()

    unicos[
        ["status_identidade", "motivo_identidade"]
    ] = unicos.apply(
        avaliar,
        axis=1,
        result_type="expand",
    )

    dados = dados.merge(
        unicos,
        on=chaves,
        how="left",
        validate="many_to_one",
    )

    dados = dados.drop(columns=chaves)

    if len(dados) != len(todas):
        raise AssertionError(
            "A validação alterou o total de registros"
        )

    return dados


def executar(uber: pd.DataFrame, mapa: pd.DataFrame, evid: pd.DataFrame,
             referencia: date) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    regras = regras_uber(uber, referencia)
    cand = expandir_mapeamento(mapa)
    cand['marca_chave'] = cand['marca_uber'].map(chave_marca)
    cand['modelo_chave'] = cand['modelo_uber'].map(normalizar)
    todas = cand.merge(regras.drop(columns=['marca_uber', 'modelo_uber']),
                       on=['marca_chave', 'modelo_chave'], how='left',
                       validate='many_to_many', indicator=True)
    if (todas['_merge'] != 'both').any():
        raise ValueError('Candidatos FIPE não vinculados a um modelo Uber')
    todas = todas.drop(columns='_merge')
    if len(todas) != len(cand) * 4:
        raise AssertionError('Perda de combinações versão×categoria')
    todas = validar_identidade_versoes(todas)
    classificacoes = todas.apply(_classificar, axis=1, result_type='expand')
    classificacoes.columns = ['status_triagem', 'motivo_triagem']
    todas[['status_triagem', 'motivo_triagem']] = classificacoes
    conflitos = (
        todas["status_identidade"] != "candidato_coerente"
    ) & (
        todas["status_categoria"] == "pendente"
    )

    todas.loc[conflitos, "status_triagem"] = "revisar_identidade"
    todas.loc[conflitos, "motivo_triagem"] = (
        todas.loc[conflitos, "motivo_identidade"]
    )
    # Aprovação final exige ano de fabricação efetivo e eventuais atributos
    # de veículo específico (ex. cor Black). Nenhuma versão aqui é elegível final.
    todas['elegibilidade_final_confirmada'] = False
    fila = todas.loc[todas['status_triagem'].isin({'pendente_comprovacao', 'pendente_tecnologia', 'pendente_vinculo_oficial'})].copy()
    consultar = todas.loc[todas['status_triagem'].eq('apto_consultar_anos_fipe')].copy()
    resumo = todas.groupby(['categoria_uber', 'status_triagem'], dropna=False).size().reset_index(name='combinacoes')
    if resumo['combinacoes'].sum() != len(todas):
        raise AssertionError('Resumo não conserva todas as combinações')
    return regras, todas, fila, consultar


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--uber', type=Path, default=Path('dados_limpos/09_UBER_MODELOS_SP.csv'))
    p.add_argument('--mapeamento', type=Path, default=Path('dados_cache/fipe_mapeamento.csv'))
    p.add_argument('--evidencias', type=Path, default=Path('dados_referencias/fipe_especificacoes_verificadas.csv'))
    p.add_argument('--saida', type=Path, default=Path('dados_relatorios'))
    p.add_argument(
        "--catalogar-anos",
        action="store_true",
    )

    p.add_argument(
        "--limite-requisicoes",
        type=int,
        default=50,
    )
    
    args = p.parse_args()
    for caminho in [args.uber, args.mapeamento]:
        if not caminho.is_file():
            p.error(f'Arquivo não encontrado: {caminho}')
    uber = pd.read_csv(args.uber)
    mapa = pd.read_csv(args.mapeamento, dtype={'brand_id': 'string'})
    evid = _ler_evidencias(args.evidencias)
    regras, todas, fila, consultar = executar(uber, mapa, evid, date(2026, 11, 6))
    args.saida.mkdir(parents=True, exist_ok=True)
    saidas = {
        'uber_regras_por_categoria_2026.csv': regras,
        'uber_fipe_triagem_2026.csv': todas,
        'uber_fipe_fila_comprovacao_2026.csv': fila,
        'uber_fipe_prontos_consulta_anos_2026.csv': consultar,
    }
    for nome, df in saidas.items():
        df.to_csv(args.saida / nome, index=False, encoding='utf-8-sig')
    print(f'Uber: {len(uber)} | Versões candidatas: {len(todas)//4} | Ligações categoria: {len(todas)}')
    print(f'Pendentes técnicos: {len(fila)} | Prontos para consultar anos: {len(consultar)}')
    print(todas.groupby(['categoria_uber', 'status_triagem']).size().to_string())
    print('AVISO: pronto para consultar anos FIPE NÃO significa elegível para Uber.')
    if args.catalogar_anos:
        catalogar_anos_fipe(
            todas,
            limite_requisicoes=args.limite_requisicoes,
        )

def catalogar_anos_fipe(
    dados: pd.DataFrame,
    limite_requisicoes: int = 50,
) -> None:
    """Consulta anos disponíveis na FIPE sem aprovar elegibilidade Uber."""

    import json
    import time
    from pathlib import Path

    import requests

    if limite_requisicoes < 0:
        raise ValueError("O limite de requisições não pode ser negativo.")

    cache_path = Path("dados_cache/fipe_catalogo.json")
    saida_path = Path(
        "dados_relatorios/fipe_anos_catalogados_2026.csv"
    )

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    saida_path.parent.mkdir(parents=True, exist_ok=True)

    if cache_path.exists():
        with cache_path.open("r", encoding="utf-8") as arquivo:
            cache = json.load(arquivo)
    else:
        cache = {"brands": None, "models": {}, "years": {}}

    cache.setdefault("years", {})

    # Consultar apenas versões associadas a uma categoria
    # efetivamente listada na fonte Uber.
    candidatas = dados.loc[
    dados["status_categoria"].eq("pendente")
    & dados["status_identidade"].eq("candidato_coerente")
   ].copy()

    versoes = candidatas[
        ["brand_id", "model_id"]
    ].drop_duplicates()

    sessao = requests.Session()
    requisicoes = 0
    encontrados_cache = 0
    erros = 0

    for row in versoes.itertuples(index=False):
        brand_id = str(row.brand_id)
        model_id = str(row.model_id)
        chave = f"{brand_id}:{model_id}"

        if chave in cache["years"]:
            encontrados_cache += 1
            continue

        if requisicoes >= limite_requisicoes:
            break

        url = (
            "https://fipe.parallelum.com.br/api/v2/cars"
            f"/brands/{brand_id}/models/{model_id}/years"
        )

        try:
            resposta = sessao.get(url, timeout=25)
            requisicoes += 1

            if resposta.status_code == 429:
                print("Limite da API atingido. Coleta interrompida.")
                break

            resposta.raise_for_status()
            anos = resposta.json()

            if not isinstance(anos, list):
                raise ValueError("Resposta FIPE não contém lista de anos.")

            cache["years"][chave] = anos

            temporario = cache_path.with_suffix(".tmp")
            with temporario.open("w", encoding="utf-8") as arquivo:
                json.dump(cache, arquivo, ensure_ascii=False)

            temporario.replace(cache_path)
            time.sleep(0.25)

        except (requests.RequestException, ValueError) as erro:
            erros += 1
            print(f"Erro ao consultar {chave}: {erro}")

    registros = []

    for row in candidatas.itertuples(index=False):
        chave = f"{row.brand_id}:{row.model_id}"

        for item in cache["years"].get(chave, []):
            codigo = str(item.get("code", ""))
            ano_texto = codigo.split("-")[0]

            ano_modelo = (
                int(ano_texto)
                if ano_texto.isdigit() and len(ano_texto) == 4
                else None
            )

            limite = pd.to_numeric(
                row.ano_min_fabricacao_regra,
                errors="coerce"
            )

            if codigo.split("-")[0] == "32000":
                ano_modelo = None
                situacao = "zero_km"

            elif ano_modelo is None:
                situacao = "codigo_ano_desconhecido"

            elif pd.isna(limite):
                situacao = "ano_minimo_ausente"

            elif ano_modelo > 2026:
                situacao = "ano_modelo_futuro"

            elif ano_modelo < limite:
                situacao = "anterior_ao_limite_de_estudo"

            else:
                situacao = "dentro_da_janela_de_estudo"

            registros.append({
                "marca_uber": row.marca_uber,
                "modelo_uber": row.modelo_uber,
                "categoria_uber": row.categoria_uber,
                "brand_id": row.brand_id,
                "model_id": row.model_id,
                "modelo_fipe": row.modelo_fipe,
                "year_code": codigo,
                "ano_modelo_fipe": ano_modelo,
                "ano_min_fabricacao_regra": limite,
                "status_ano_catalogo": situacao,
                "elegibilidade_uber_confirmada": False,
            })

    resultado = pd.DataFrame(registros)

    if not resultado.empty:
        chaves = [
            "marca_uber",
            "modelo_uber",
            "categoria_uber",
            "brand_id",
            "model_id",
            "year_code",
        ]

        if resultado.duplicated(chaves).any():
            raise ValueError("Foram encontrados anos FIPE duplicados.")

    resultado.to_csv(
        saida_path,
        index=False,
        encoding="utf-8-sig"
    )

    print(f"Versões distintas na fila: {len(versoes)}")
    print(f"Encontradas no cache: {encontrados_cache}")
    print(f"Novas requisições: {requisicoes}")
    print(f"Erros: {erros}")
    print(f"Linhas de anos catalogados: {len(resultado)}")
    print(f"Arquivo gerado: {saida_path}")
    print("ATENÇÃO: os anos FIPE não comprovam elegibilidade Uber.")


if __name__ == '__main__':
    main()
