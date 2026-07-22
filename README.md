# SRAG Health Monitor

Sistema para gerar relatórios epidemiológicos de SRAG a partir de dados
DATASUS/SIVEP-Gripe, com API HTTP, execução assíncrona por worker, auditoria,
guardrails e geração de gráficos.

## Visão Geral

O projeto evoluiu de uma PoC para uma base de produto operável:

- API FastAPI para criar e consultar jobs de relatório.
- Worker separado para executar jobs pendentes.
- Pipeline multiagente: ingestão SUS, análise epidemiológica e escrita de relatório.
- Persistência de jobs em SQLite.
- Banco SRAG em SQLite.
- Relatórios Markdown e gráficos em `outputs/reports`.
- Logs estruturados de auditoria em `outputs/logs`.
- Docker Compose com serviços `api` e `worker`.
- CI com testes, build Docker e smoke test de healthcheck.

## Arquitetura

```text
Cliente/API Consumer
        |
        v
FastAPI (/reports, /reports/{job_id}, /reports/{job_id}/artifact, /metrics)
        |
        v
SQLite jobs store (data/jobs.db)
        |
        v
Worker
        |
        v
GenerateReportService / Multi-Agent Orchestrator
        |
        v
Blackboard de etapas (estado por execução em data/pipeline_state/)
        |
        +--> collect_data  ─┐ (paralelo)  SUSDataIngestionAgent -> data/srag.db
        +--> collect_news  ─┘             SUSDataIngestionAgent -> feeds RSS
        +--> analyze                      EpidemiologyAnalysisAgent -> achados e risco
        +--> generate_charts              ReportWriterAgent -> gráficos
        +--> write_report                 ReportWriterAgent -> Markdown
        +--> AuditLogger -> outputs/logs
```

As etapas não se chamam entre si: cada uma declara pré-condições sobre o
estado compartilhado e roda quando elas são satisfeitas (coordenação por
blackboard). O progresso é persistido por etapa — reexecutar com o mesmo
`execution_id` retoma do ponto da falha sem refazer o que já foi concluído.

## Estrutura

```text
src/
  api/                 # FastAPI app
  services/            # casos de uso, job store e worker
  agents/              # orquestrador multiagente e agentes especializados
  tools/               # banco, notícias e gráficos
  database/            # gerenciador SQLite SRAG
  guardrails/          # validações, LGPD e auditoria
  utils/               # processamento DATASUS
main.py                # CLI síncrono
worker.py              # processo worker
Dockerfile
docker-compose.yml
Makefile
```

## Requisitos

- Python 3.11+
- Docker/Compose opcional para execução containerizada
- `data/srag.db` para gerar relatórios reais

`OPENAI_API_KEY` é opcional: com a chave configurada, as seções narrativas do
relatório (análise contextual e conclusões/recomendações) são escritas pelo
LLM (`SRAG_MODEL`, default `gpt-4.1-mini`) a partir dos achados calculados
deterministicamente; sem a chave — ou em caso de falha na chamada — o relatório
cai no modo determinístico baseado em regras. O modo usado fica registrado na
seção "Fonte e Rastreabilidade" de cada relatório.

As métricas, achados e nível de risco são sempre calculados por código
determinístico; o LLM escreve apenas a narrativa, com instruções de não
inventar números e sem acesso a dados de pacientes. O texto gerado passa pelos
mesmos guardrails de validação de conteúdo e anonimização de PII.

## Setup Local

```bash
make install
```

Opcionalmente copie o arquivo de ambiente:

```bash
cp .env.example .env
```

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

Ingerir dados oficiais do SUS/OpenDATASUS antes de gerar relatórios reais:

```bash
SRAG_SUS_DATA_URL="https://..." make ingest
```

Para smoke test com amostra:

```bash
.venv/bin/python ingest.py --source-url "https://..." --nrows 1000
```

Quando `SRAG_API_KEY` estiver configurada, envie o cabeçalho:

```bash
curl http://localhost:8000/reports \
  -H "X-API-Key: $SRAG_API_KEY"
```

## Rodar Com Docker

```bash
make docker-up
```

Parar:

```bash
make docker-down
```

## API

`GET /health` e `GET /ready` são públicos para healthchecks. Os demais
endpoints exigem `X-API-Key` quando `SRAG_API_KEY` estiver configurada.

### `GET /health`

Retorna status básico da API.

```json
{"status": "ok"}
```

### `GET /ready`

Retorna readiness operacional, incluindo acesso ao banco de jobs, diretórios
graváveis e presença de `data/srag.db`.

### `GET /reports`

Lista jobs recentes.

Query params:

- `limit`: 1 a 100, default `20`
- `status`: `queued`, `running`, `succeeded` ou `failed`

### `POST /reports`

Cria um job assíncrono.

Payload opcional:

```json
{
  "model": "gpt-4.1-mini",
  "db_path": "data/srag.db",
  "output_dir": "outputs/reports"
}
```

Resposta:

```json
{
  "job_id": "uuid",
  "status": "queued",
  "status_url": "/reports/uuid"
}
```

### `GET /reports/{job_id}`

Consulta status e resultado do job.

Estados possíveis:

- `queued`
- `running`
- `succeeded`
- `failed`

### `GET /reports/{job_id}/artifact`

Baixa o relatório Markdown gerado por um job concluído.

Retornos comuns:

- `200`: relatório disponível
- `409`: job ainda não concluído
- `404`: job ou artefato não encontrado

### `GET /metrics`

Retorna métricas operacionais simples:

```json
{
  "total_jobs": 10,
  "jobs_by_status": {
    "queued": 1,
    "running": 0,
    "succeeded": 8,
    "failed": 1
  },
  "recent_failures": []
}
```

### `POST /reports/sync`

Executa geração síncrona. Útil para debug e integração interna.

## CLI

Ingestão de dados oficiais:

```bash
.venv/bin/python ingest.py --source-url "https://..."
```

Geração síncrona via CLI:

```bash
.venv/bin/python main.py --output-dir outputs/reports
```

Processar no máximo um job pendente:

```bash
make worker-once
```

## Variáveis De Ambiente

| Variável | Default | Descrição |
| --- | --- | --- |
| `OPENAI_API_KEY` | vazio | chave OpenAI opcional |
| `SRAG_API_KEY` | vazio | chave opcional para proteger endpoints HTTP |
| `SRAG_DATA_DIR` | `./data` | diretório de dados |
| `SRAG_DB_PATH` | `./data/srag.db` | banco SRAG |
| `SRAG_JOBS_DB_PATH` | `./data/jobs.db` | banco de jobs |
| `SRAG_OUTPUT_DIR` | `./outputs/reports` | relatórios e gráficos |
| `SRAG_LOG_DIR` | `./outputs/logs` | logs de auditoria |
| `SRAG_MODEL` | `gpt-4.1-mini` | modelo configurado |
| `SRAG_SUS_DATA_URL` | vazio | URL do recurso CSV SRAG no portal oficial |
| `SRAG_SUS_INGEST_NROWS` | vazio | limite opcional de linhas para smoke tests |
| `SRAG_NEWS_FEEDS` | vazio | JSON opcional para sobrescrever os feeds RSS de notícias |

## Validação

```bash
make compile
make test
make docker-config
```

## Dados

O sistema espera um banco SQLite em `data/srag.db`. Se o banco não existir, o
job falha explicitamente com status `failed`. Gere esse cache com `make ingest`
apontando `SRAG_SUS_DATA_URL` para o recurso CSV publicado no portal oficial.

Dados brutos e processados do DATASUS não são versionados no repositório.

Fonte de referência:

- OpenDATASUS/SIVEP-Gripe: https://opendatasus.saude.gov.br/dataset/srag-2021-a-2024
- Portal atual de dados abertos do SUS: https://dadosabertos.saude.gov.br

## Notícias

As notícias dos relatórios são obtidas em tempo de execução de feeds RSS de
fontes reconhecidas em vigilância epidemiológica no Brasil:

- Agência Fiocruz de Notícias (inclui os boletins InfoGripe): `https://agencia.fiocruz.br/rss.xml`
- Agência Brasil / EBC — editoria de Saúde: `https://agenciabrasil.ebc.com.br/rss/saude/feed.xml`

Os itens são ordenados por relevância ao tema de SRAG/vírus respiratórios e por
data. Em caso de falha de rede ou parsing, a busca degrada para uma lista vazia
— o sistema nunca fabrica notícias nem estatísticas.

Os feeds podem ser sobrescritos pela variável `SRAG_NEWS_FEEDS` (JSON), por
exemplo:

```bash
SRAG_NEWS_FEEDS='[{"name":"Agência Fiocruz","url":"https://agencia.fiocruz.br/rss.xml"}]'
```

## Governança

- Logs estruturados em JSONL.
- Validação de entrada para consultas e períodos.
- Validação de conteúdo do relatório.
- Detecção e anonimização de PII em texto gerado.
- Rastreamento de erros e status por job.
- Métricas operacionais por status de job.
- Separação entre ingestão de dados, análise epidemiológica e narrativa.

## Documentação

- [Runbook operacional](docs/runbook.md)
- [Plano de productização](docs/productization_plan.md)
- [Informações DATASUS](docs/datasus_info.md)
- [Diagrama de arquitetura](docs/architecture_diagram.mmd)
