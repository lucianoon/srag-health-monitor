# Plano de Productização

Este plano transforma o SRAG Health Monitor de PoC em produto escalável,
operável e evolutivo.

## 1. Fundação Reprodutível

- Centralizar configuração de caminhos, modelo, banco, relatórios e logs.
- Remover caminhos absolutos e dependência de um ambiente único.
- Garantir CLI funcional sem carregar dependências pesadas desnecessariamente.
- Padronizar diretórios de runtime via variáveis de ambiente:
  - `SRAG_DATA_DIR`
  - `SRAG_DB_PATH`
  - `SRAG_OUTPUT_DIR`
  - `SRAG_LOG_DIR`
  - `SRAG_MODEL`

## 2. API de Produto

- Criar uma API HTTP para geração, consulta e listagem de relatórios.
- Separar execução síncrona curta de jobs assíncronos demorados.
- Adicionar contratos de entrada/saída com Pydantic.
- Retornar status de execução com `execution_id`.

## 3. Pipeline de Dados

- Transformar processamento DATASUS em comando idempotente.
- Validar schema dos arquivos brutos antes da carga.
- Versionar metadados de carga: fonte, data, quantidade de linhas e checksums.
- Preparar troca de SQLite para PostgreSQL sem reescrever domínio.
- Separar o pipeline em agentes especializados:
  - `SUSDataIngestionAgent`: coleta, valida e registra fonte dos dados.
  - `EpidemiologyAnalysisAgent`: calcula achados e nível de risco.
  - `ReportWriterAgent`: gera gráficos e relatório narrativo.

## 4. Execução Assíncrona

- Criar fila de jobs para geração de relatórios e atualização de dados.
- Tornar ferramentas independentes de estado global.
- Persistir status, erros e duração de cada etapa.
- Usar SQLite como store persistente inicial para jobs.
- Separar API e worker: a API cria jobs e o worker executa jobs pendentes.
- Evoluir para Redis/Postgres e workers dedicados quando houver múltiplas
  instâncias da API.

## 5. Observabilidade

- Padronizar logs estruturados em JSON.
- Expor métricas de execução: duração, falhas, volume processado e chamadas externas.
- Adicionar correlation id em todas as etapas.
- Separar logs de auditoria de logs técnicos.
- Expor healthcheck, readiness e listagem de jobs recentes.

## 6. Governança e Segurança

- Aplicar validações de entrada nas fronteiras do sistema.
- Adicionar política explícita para dados sensíveis e retenção.
- Evitar simulações silenciosas em produção; mocks devem ser configuráveis.
- Registrar fonte e timestamp de notícias/dados usados em relatórios.

## 7. Deploy

- Adicionar Dockerfile e compose para ambiente local completo.
- Definir healthchecks para API, banco e workers.
- Criar pipeline CI com lint, testes, build e smoke test.
- Publicar artefatos de relatório em storage configurável.

## Execução Local Com Docker

1. Copie `.env.example` para `.env` e ajuste as variáveis necessárias.
2. Garanta que `data/srag.db` exista antes de gerar relatórios.
3. Suba API e worker:

```bash
docker compose up --build
```

4. Crie um job:

```bash
curl -X POST http://localhost:8000/reports \
  -H "Content-Type: application/json" \
  -d '{}'
```

5. Consulte o status retornado em `status_url`.

## Operação

Use o [runbook](runbook.md) para comandos locais, Docker, smoke tests e
troubleshooting.

## Próximo Marco

O corte de jobs assíncronos já foi iniciado com store persistente em SQLite,
endpoints de status, worker separado e Docker Compose. O próximo marco
recomendado é transformar a ingestão configurável por `SRAG_SUS_DATA_URL` em
um job assíncrono dedicado, com agendamento, histórico de cargas e metadados de
versão/checksum da fonte oficial OpenDATASUS/SIVEP-Gripe.
