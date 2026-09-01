# Como contribuir

## Ambiente

```bash
make install                 # uv sync --locked
cp .env.example .env         # opcional: OPENAI_API_KEY e caminhos
```

O `.env` é ignorado pelo git. Nunca faça commit de chaves nem de dados de
pacientes, mesmo anonimizados.

## Antes de abrir o PR

```bash
make check                   # ruff + mypy + pytest, o mesmo que o CI roda
make docker-config           # valida o docker-compose.yml
```

A suíte não faz chamada de rede nem exige chave de API. Um teste que precise
de rede está errado: injete a dependência ou use o fallback determinístico.

## O que o CI exige

- `ruff check .` sem avisos e `mypy` sem erros.
- `pytest -q` verde.
- A imagem Docker constrói, a API sobe e `GET /health` responde.

## Dependências

Adicione ao `pyproject.toml` e rode `uv lock`. Faça commit do `uv.lock` junto:
o CI usa `uv sync --locked` e falha se o lock estiver desatualizado.

## Escopo

Métricas, achados e nível de risco são calculados por código determinístico.
Mudanças que deleguem qualquer número ao LLM serão recusadas; o modelo escreve
apenas a narrativa. Veja `SECURITY.md` para relatar vulnerabilidades.
