# Runbook Operacional

## Setup Local

```bash
make install
```

Configure `.env` a partir de `.env.example` quando precisar sobrescrever paths
ou informar `OPENAI_API_KEY`.

Para proteger endpoints operacionais da API, configure:

```bash
SRAG_API_KEY=troque-este-valor
```

Quando a chave estiver configurada, envie `X-API-Key` em chamadas como
`/reports`, `/metrics` e `/reports/<job_id>/artifact`.

## Ingestão De Dados SUS

Configure a URL do recurso CSV SRAG publicado no portal oficial de dados
abertos do SUS:

```bash
SRAG_SUS_DATA_URL="https://..."
```

Rodar ingestão completa:

```bash
make ingest
```

Smoke test com limite de linhas:

```bash
.venv/bin/python ingest.py --source-url "https://..." --nrows 1000
```

A ingestão baixa o arquivo para `data/raw/`, processa para
`data/processed/srag_processed.csv`, recria o cache `data/srag.db` e grava
metadados em `data/ingestion_metadata.json`.

## Rodar Sem Docker

Terminal 1:

```bash
make api
```

Terminal 2:

```bash
make worker
```

Healthcheck:

```bash
make smoke
```

Readiness:

```bash
curl http://localhost:8000/ready
```

Criar job:

```bash
curl -X POST http://localhost:8000/reports \
  -H "Content-Type: application/json" \
  -d '{}'
```

Consultar status:

```bash
curl http://localhost:8000/reports/<job_id>
```

Listar jobs recentes:

```bash
curl http://localhost:8000/reports
```

Exemplo autenticado:

```bash
curl http://localhost:8000/metrics \
  -H "X-API-Key: $SRAG_API_KEY"
```

Métricas operacionais:

```bash
curl http://localhost:8000/metrics
```

Baixar relatório concluído:

```bash
curl -OJ http://localhost:8000/reports/<job_id>/artifact
```

## Rodar Com Docker

```bash
make docker-up
```

Parar e limpar volumes:

```bash
make docker-down
```

## Validação

```bash
make compile
make test
make docker-config
```

## Dados Necessários

O relatório depende de `data/srag.db`. Se o banco não existir, o job falha de
forma explícita com status `failed`.

Paths padrão:

- Dados: `data/`
- Banco SRAG: `data/srag.db`
- Banco de jobs: `data/jobs.db`
- Relatórios: `outputs/reports/`
- Logs: `outputs/logs/`

## Troubleshooting

Docker/OrbStack não está rodando:

```text
failed to connect to the docker API ... docker.sock
```

Abra Docker Desktop ou OrbStack e rode novamente:

```bash
make docker-build
```

Matplotlib tenta usar backend gráfico:

```bash
export MPLBACKEND=Agg
```

Banco ausente:

```text
Banco de dados não encontrado em data/srag.db
```

Execute `make ingest` com `SRAG_SUS_DATA_URL` configurada ou aponte
`SRAG_DB_PATH` para um banco existente.

Fonte SUS não configurada:

```text
Fonte SUS não configurada
```

Informe `--source-url` no `ingest.py` ou configure `SRAG_SUS_DATA_URL`.

Chave de API ausente ou inválida:

```text
API key inválida ou ausente
```

Confira se `SRAG_API_KEY` está configurada no serviço e envie o mesmo valor no
cabeçalho `X-API-Key`.

Artefato indisponível:

```text
Relatório ainda não está disponível
```

Confirme se o job está com status `succeeded` antes de chamar
`/reports/<job_id>/artifact`.
