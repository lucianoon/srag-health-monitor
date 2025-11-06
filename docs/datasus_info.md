# Informações sobre Dados DATASUS - SRAG

## Fonte de Dados
- **URL**: https://opendatasus.saude.gov.br/dataset/srag-2021-a-2024
- **Sistema**: SIVEP-Gripe (Sistema de Informação da Vigilância Epidemiológica da Gripe)
- **Atualização**: Semanal (banco "vivo" para ano atual)

## Recursos Disponíveis

### Documentação
1. **Dicionário de Dados**: PDF com descrição de todas as variáveis
2. **Ficha de Notificação**: Formulário utilizado para coleta

### Dados por Ano
- **2019**: Banco congelado (26/06/2025) - CSV, JSON, Parquet, XML
- **2020**: Banco congelado (26/06/2025) - CSV, JSON, Parquet, XML
- **2021**: Banco congelado (26/06/2025) - CSV, JSON, Parquet, XML
- **2022**: Banco congelado (26/06/2025) - CSV, JSON, Parquet, XML
- **2023**: Banco congelado (26/06/2025) - CSV, JSON, Parquet, XML
- **2024**: Banco congelado (26/06/2025) - CSV, JSON, Parquet, XML
- **2025**: Banco "vivo" - atualizado semanalmente

## Características dos Dados
- **Formato**: CSV com ~100 colunas e ~165.000 linhas
- **Granularidade Geográfica**: Município
- **Granularidade Temporal**: Dia
- **Cobertura**: Nacional (Brasil)
- **Anonimização**: Dados tratados conforme LGPD

## Observações Importantes
1. Dados sujeitos a erros de digitação e preenchimento
2. Revisões contínuas realizadas pelas equipes de vigilância
3. Muitos valores ausentes e problemas de qualidade
4. Necessário tratamento e seleção de colunas relevantes

## Colunas Relevantes para o Projeto
Baseado nos requisitos, as colunas principais serão:
- **DT_NOTIFIC**: Data de notificação
- **DT_SIN_PRI**: Data dos primeiros sintomas
- **SG_UF**: Unidade Federativa
- **ID_MUNICIP**: Código do município
- **CS_SEXO**: Sexo
- **NU_IDADE_N**: Idade
- **EVOLUCAO**: Evolução do caso (cura/óbito)
- **UTI**: Internação em UTI (sim/não)
- **VACINA**: Vacinação (sim/não)
- **CLASSI_FIN**: Classificação final
- **DT_EVOLUCA**: Data da evolução

## Estratégia de Download
Para a PoC, utilizaremos dados de 2024 (banco congelado) que contém volume significativo e está estabilizado.
