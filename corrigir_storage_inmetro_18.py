"""Corrige problemas de seleção S3 e de ingestão ANEEL/INMETRO no PI06.

Execute na raiz do repositório: python corrigir_storage_inmetro_18.py
Faz backup uma única vez em dados_cache/correcoes_18; não altera RAW/CSV existentes.
"""
from __future__ import annotations

import ast
import re
import shutil
from pathlib import Path

ROOT = Path.cwd()
BACKUP = ROOT / 'dados_cache' / 'correcoes_18'

INMETRO = '''def processar_inmetro() -> None:
    """Lê a planilha organizada do INMETRO, preservando nulos e fonte RAW."""
    candidatos = localizar_todos(["INMETRO/**/*.xlsx"])
    organizados = [
        p for p in candidatos
        if normalizar_texto(p.stem) == "DADOS INMETRO ORGANIZADO"
    ]
    if len(organizados) != 1:
        raise FileNotFoundError(
            "INMETRO: esperado exatamente um arquivo de dados organizados "
            "na referência selecionada. Encontrados: "
            f"{[str(p) for p in organizados]}. "
            f"Todos os XLSX: {[p.name for p in candidatos]}"
        )

    origem = organizados[0]
    colunas_esperadas = [
        "categoria", "marca", "modelo", "versao", "motor",
        "tipo_propulsao", "consumo_energetico_mj_km",
        "autonomia_eletrica_km", "linha_origem_excel",
    ]
    # Aceita variantes de nome de aba, mas nunca assume a primeira aba.
    with pd.ExcelFile(origem) as excel:
        preferidas = [
            nome for nome in excel.sheet_names
            if normalizar_texto(nome) in {
                "DADOS ORGANIZADOS", "DADOS INMETRO ORGANIZADO"
            }
        ]
        if not preferidas:
            raise ValueError(
                f"INMETRO: aba organizada não encontrada em {origem.name}. "
                f"Abas disponíveis: {excel.sheet_names}"
            )
        if len(preferidas) != 1:
            raise ValueError(
                f"INMETRO: abas organizadas ambíguas: {preferidas}"
            )
        aba = preferidas[0]
        df = pd.read_excel(excel, sheet_name=aba, dtype=object)

    df.columns = [str(col).strip() for col in df.columns]
    faltantes = sorted(set(colunas_esperadas) - set(df.columns))
    if faltantes:
        raise ValueError(
            f"INMETRO: aba {aba!r} sem as colunas {faltantes}"
        )
    if df.empty:
        raise ValueError("INMETRO: aba organizada sem registros")

    chave = ["marca", "modelo", "versao", "motor", "tipo_propulsao"]
    grupos_repetidos = int(df.duplicated(subset=chave, keep=False).sum())
    vazios = df.isna().sum()
    destino = salvar_csv(df, "05_INMETRO_ORGANIZADO.csv")
    registrar_coleta(
        "INMETRO_PBEV", origem, destino, len(df),
        observacao=(
            f"Planilha organizada, aba={aba}; "
            "nulos e marcadores originais preservados; "
            f"{grupos_repetidos} linhas em grupos de chave repetida."
        ),
    )
    print(
        f"[OK] INMETRO | arquivo={origem.name} | aba={aba} | "
        f"registros={len(df)} | duplicidade_de_chave={grupos_repetidos} | "
        f"colunas_com_nulos={int((vazios > 0).sum())} | saida={destino}"
    )

'''


def replace_function(code: str, func_name: str, new_code: str) -> str:
    """Substitui só uma função de topo; não reescreve outras partes."""
    tree = ast.parse(code)
    matches = [x for x in tree.body if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)) and x.name == func_name]
    if len(matches) != 1:
        raise RuntimeError(f"Esperada uma função de topo {func_name}: {len(matches)}")
    node = matches[0]
    lines = code.splitlines(keepends=True)
    return ''.join(lines[:node.lineno - 1]) + new_code + ''.join(lines[node.end_lineno:])


def patch_storage(code: str) -> str:
    # O bug atual: inclusão no plano somente dentro do if uber_match.
    # Encontra apenas o bloco de inclusão no plano que foi recuado para o ramo Uber Match.
    matcher = re.compile(
        r'(?P<tail>            _destino_seguro\(Path\(tempfile\.gettempdir\(\)\), fonte, relativo\)\n'
        r'            if chave in chaves_vistas:\n'
        r'                raise ValueError\([^\n]*\)\n'
        r'            chaves_vistas\.add\(chave\)\n'
        r'            plano\.append\(\(chave, relativo\)\)\n)'
    )
    m = matcher.search(code)
    if not m:
        raise RuntimeError('storage_workspace.py: bloco de planejar_fonte mudou. Nada foi modificado.')
    # Proteção: exige que o bloco esteja dentro do if uber_match.
    inicio = code.rfind('        if fonte.codigo == "uber_match":', 0, m.start())
    limite = code.rfind('    if not plano:', 0, m.start())
    if inicio < 0 or limite > inicio:
        raise RuntimeError('storage_workspace.py: bloco não está dentro do if Uber Match')
    fixed = ''.join(line[4:] if line.startswith('    ') else line for line in m.group('tail').splitlines(keepends=True))
    result = code[:m.start('tail')] + fixed + code[m.end('tail'):]
    return result


def patch_bases(code: str) -> str:
    # Erro remanescente no repositório: def processar_ibge dentro de processar_anp.
    if '\n    def processar_ibge() -> None:' in code:
        code = code.replace('\n    def processar_ibge() -> None:', '\ndef processar_ibge() -> None:', 1)
    code = replace_function(code, 'processar_inmetro', INMETRO)
    # ANEEL: ausência não pode gerar sucesso aparente e deve relatar a saída.
    code = re.sub(
        r'(?m)^(    if not origem:\n)        print\("ANEEL: arquivo não encontrado\."\)\n        return\n',
        '    if not origem:\n        raise FileNotFoundError("ANEEL: arquivo não encontrado no workspace")\n',
        code, count=1,
    )
    anchor = '''    registrar_coleta(
        "ANEEL",
        origem,
        destino,
        len(df),
        observacao=observacao,
    )'''
    if anchor not in code:
        raise RuntimeError('extrair_bases.py: registro de coleta ANEEL mudou. Nada foi modificado.')
    code = code.replace(anchor, anchor + '\n    print(f"[OK] ANEEL | registros={len(df)} | saida={destino} | {observacao}")', 1)
    # ANP: se todas as fontes falharem, a função não deve terminar silenciosamente.
    code = code.replace('''    if not dfs:
        return''', '''    if not dfs:
        raise RuntimeError("ANP: nenhum arquivo processado com sucesso")''', 1)
    # Garante que a função IBGE exista em nível de módulo.
    tree = ast.parse(code)
    functions = {x.name for x in tree.body if isinstance(x, ast.FunctionDef)}
    if 'processar_ibge' not in functions:
        raise RuntimeError('IBGE não está no nível do módulo')
    return code


def main() -> None:
    paths = [ROOT / 'storage_workspace.py', ROOT / 'extrair_bases.py']
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(path)
    originals = [p.read_text(encoding='utf-8') for p in paths]
    updated = [patch_storage(originals[0]), patch_bases(originals[1])]
    for p, source in zip(paths, updated):
        compile(source, str(p), 'exec')
    BACKUP.mkdir(parents=True, exist_ok=True)
    for path, before, after in zip(paths, originals, updated):
        backup = BACKUP / path.name
        if not backup.exists():
            shutil.copy2(path, backup)
        path.write_text(after, encoding='utf-8')
        print(f'[OK] corrigido: {path.name} | backup={backup}')
    print('Correções aplicadas; executar: python extrair.py bases --origem storage')


if __name__ == '__main__':
    main()
