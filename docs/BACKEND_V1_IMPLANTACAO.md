# Implantação e validação — API v1 do PI06

## Infraestrutura

Backend Python FastAPI, PostgreSQL com extensão PostGIS, Supabase como provedor do banco. A API lê apenas o schema `api_v1`. O ETL `backend/carga.py` escreve **somente** nesse schema, exceto por criar a extensão PostGIS (se ainda não existir) e o próprio schema. Não dispara `DROP TABLE` nem modifica `fato`, `analytics`, `geo` ou `metadata` pré-existentes.

**PostGIS no Supabase:** ative primeiro no Dashboard > Database > Extensions, preferencialmente no schema `extensions`. A migration 006 também usa esse schema se precisar criar a extensão. SQL e conexão FastAPI colocam `extensions` no `search_path`. Se o projeto já instalou PostGIS em `public`, a migration não tenta migrar a extensão existente.

**Conexão Supabase:** no Dashboard clique `Connect` e copie a string real do método escolhido. Para migração/carga, prefira a conexão direta (se houver IPv6) ou session pooler quando necessário; para servidor persistente use conexão direta ou session pooler. O modo transaction pooler não é o padrão deste pacote: ele pode exigir desativação de prepared statements. Não tente compor o hostname do pooler a partir da região.

> Documentação oficial: https://supabase.com/docs/guides/database/connecting-to-postgres e https://supabase.com/docs/guides/database/extensions/postgis

## Credenciais e princípio de menor privilégio

Use contas/segredos distintos:

- `DATABASE_URL`: papel de carga com autorização de DDL/importação no **ambiente de desenvolvimento**. Nunca no frontend.
- `PI06_API_DATABASE_URL`: papel de **somente leitura** do schema `api_v1`. Não usar `postgres`/superusuário/`service_role` para a API em produção.
- `PI06_CORS_ORIGINS`: lista exata de origins HTTPS autorizadas, separadas por vírgulas (local: `http://localhost:5173,http://localhost:3000`). Não habilite curingas.

Depois de criar o papel de leitura no painel SQL privado ou via administração do Postgres, conceda apenas:

```sql
GRANT USAGE ON SCHEMA api_v1 TO pi06_api_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA api_v1 TO pi06_api_reader;
-- Para cargas posteriores/novas tabelas criadas pelo mesmo proprietário:
ALTER DEFAULT PRIVILEGES IN SCHEMA api_v1 GRANT SELECT ON TABLES TO pi06_api_reader;
```

`pi06_api_reader` é apenas um nome sugerido: **o papel deve ser criado com senha secreta fora do repositório** antes dos GRANTs. Faça revisão de políticas de acesso/regras da organização e mantenha o schema `api_v1` fora da lista de schemas diretamente expostos por PostgREST até revisar RLS/grants. A API FastAPI é o ponto de acesso público pretendido, não uma conexão SQL no navegador.

## Checklist de pré-publicação

1. Confirmar `.env` ignorado; não registrar credenciais em logs ou commits.
2. Confirmar `python -m unittest discover -s testes -t . -p 'test_*.py' -v` sem falhas.
3. Confirmar `python -m backend.carga --validar` e SHA-256 do manifesto.
4. Confirmar GeoJSON com 527 zonas e 39 municípios; geometrias EPSG:4326 e sem áreas alteradas acima do limite de revisão cartográfica.
5. Confirmar OCM snapshot e datas da coleta; não anunciar funcionamento instantâneo.
6. Fazer backup e `python -m backend.carga --publicar` em banco separado do ambiente de produção.
7. Consultar carga: `SELECT versao,contagens,zonas_com_geometria,pontos_recarga FROM api_v1.carga_atual;`.
8. Conferir contagens via SQL (`COUNT(*)`): 527 zonas, 39 municípios, 96 distritos capital, 838 energias, 1.676 motoristas, 3 premissas e 5.028 sensibilidades, se baseline igual ao de novembro/2026.
9. Validar `SELECT count(*) FROM api_v1.zonas_geometrias WHERE NOT ST_IsValid(geom);` igual a zero e `SELECT count(*) FROM api_v1.recarga_zonas WHERE situacao='AMBIGUO';` (pode ser maior que zero; auditar).
10. Iniciar FastAPI local, consultar `/docs`, `/api/v1/meta`, 39 municípios e GeoJSON, depois conferir uma zona e o comparador.
11. Testar com papel de leitura que comandos de escrita na conexão da API não sejam permitidos.
12. Para produção: HTTPS, rate limiting externo, paginação, log estruturado sem segredos, monitoramento, política de segurança e revisão de acesso ao banco.

## SQL de qualidade após carga

```sql
SELECT 'municipios' tabela, COUNT(*) linhas FROM api_v1.od_municipios
UNION ALL SELECT 'zonas', COUNT(*) FROM api_v1.od_zonas
UNION ALL SELECT 'distritos', COUNT(*) FROM api_v1.od_distritos_capital
UNION ALL SELECT 'energia', COUNT(*) FROM api_v1.energia_inmetro
UNION ALL SELECT 'motorista', COUNT(*) FROM api_v1.motorista_custos
UNION ALL SELECT 'sensibilidade', COUNT(*) FROM api_v1.sensibilidade_receita
UNION ALL SELECT 'geo_zonas', COUNT(*) FROM api_v1.zonas_geometrias
UNION ALL SELECT 'geo_municipios', COUNT(*) FROM api_v1.municipios_geometrias;

SELECT COUNT(*) AS resultados_incorretos
FROM api_v1.sensibilidade_receita
WHERE componentes_custos_pendentes > 0
  AND resultado_economico_simulado_rs_mes IS NOT NULL;
```

**Esperado:** `resultados_incorretos = 0` sempre. Não substitua NULL por zero.

## Evolução planejada

- O schema `api_v1` é um snapshot adequado para o primeiro frontend. Depois que as bases 001–005 forem carregadas, as rotas poderão consultar views canônicas versionadas, mantendo o contrato de API.
- Otimizar geometrias (simplificações cartográficas controladas, tiles ou cache) antes de tráfego elevado. O endpoint municipal retorna contornos derivados das zonas; o de zonas pagina 50 geometrias por requisição no máximo.
- O projeto não precisa cruzar `zona_od_id × inmetro_id` como observação factual. O comparador faz duas leituras separadas e comunica essa separação.
