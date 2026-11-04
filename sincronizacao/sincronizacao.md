# Acesso e sincronização de dados

Este documento apresenta as instruções para acessar o Supabase Storage e baixar as bases de dados utilizadas no projeto PI06 — Visualização de Dados.

O procedimento pode ser utilizado por qualquer pessoa que tenha recebido autorização de acesso ao armazenamento.

## 1. Requisitos

Para realizar a sincronização, é necessário:

- Python instalado;
- acesso autorizado ao projeto Supabase;
- credenciais de acesso S3 do Supabase;
- scripts `storage_utils.py` e `sincronizar_storage.py`;
- dependências Python instaladas conforme o `requirements.txt`.

## 2. Configuração do acesso

O acesso ao Supabase não é público. Para obter as credenciais, é necessário solicitá-las ao responsável pela administração do armazenamento.

Na raiz do projeto, crie um arquivo `.env`, utilizando o `.env.example` como modelo.

Preencha as seguintes variáveis:

```env
S3_BUCKET=pi06-raw
S3_ENDPOINT_URL=https://SEU_PROJECT_REF.storage.supabase.co/storage/v1/s3
S3_REGION=us-east-1
S3_ACCESS_KEY_ID=SUA_ACCESS_KEY
S3_SECRET_ACCESS_KEY=SUA_SECRET_KEY
```

As credenciais devem ser fornecidas por um administrador autorizado do projeto.

**Segurança:**
- Não compartilhe suas credenciais.
- Não publique o arquivo `.env`.
- Não coloque tokens ou chaves diretamente nos scripts.
- Não envie credenciais em commits ou solicitações públicas.

## 3. Verificar o acesso

Execute:

```bash
python storage_utils.py testar
```

Para visualizar os arquivos disponíveis:

```bash
python storage_utils.py listar --prefixo raw/
```

## 4. Simular a sincronização

Antes de realizar o download, recomenda-se executar uma simulação:

```bash
python sincronizar_storage.py --prefixo raw/ --destino dados/raw/ --dry-run
```

O comando apresenta os arquivos que seriam baixados, sem transferi-los.

## 5. Baixar os arquivos

Para baixar os arquivos:

```bash
python sincronizar_storage.py --prefixo raw/ --destino dados/raw/
```

Também é possível sincronizar somente uma fonte específica. Por exemplo:

```bash
python sincronizar_storage.py --prefixo raw/abve/ --destino dados/raw/abve/
```

Para evitar sobrescrever arquivos que já existem localmente:

```bash
python sincronizar_storage.py --prefixo raw/ --destino dados/raw/ --nao-sobrescrever
```

**Atenção:** a sincronização pode baixar arquivos de diferentes formatos e tamanhos. Confira o resultado da simulação antes de executar o download.

## 6. Utilização dos dados

Após o download, os arquivos podem ser utilizados nos processos de extração, tratamento e atualização das bases CSV do projeto.

Confira os arquivos gerados e valide os dados antes de substituir qualquer base utilizada pela aplicação.

## 7. Limpeza dos arquivos temporários

Após concluir a atualização e validar os CSVs, os arquivos brutos baixados podem ser excluídos da máquina local, caso não sejam mais necessários.

Os scripts Python devem ser mantidos para futuras sincronizações.

A exclusão dos arquivos locais não remove os arquivos armazenados no Supabase Storage.

## 8. Observações

- O procedimento de sincronização é opcional.
- Os dados brutos não precisam ser enviados ao GitHub.
- O Supabase Storage permanece como repositório dos arquivos disponibilizados.
- A disponibilidade dos dados depende das permissões concedidas pelo administrador.