# 02 — Convenções e padrões

## Nomes de itens Fabric
| Tipo | Prefixo | Exemplo |
|---|---|---|
| Workspace | `WS_<projeto>_<AMB>` | `WS_Marketing360_DEV` |
| Lakehouse | `LH_<camada>` | `LH_Bronze`, `LH_Silver` |
| Warehouse | `WH_<camada>` | `WH_Gold` |
| Notebook | `NB_<nn>_<Ação>` (nn = ordem: 0x orquestração, 1x bronze, 2x silver, 3x manutenção, 4x consumo) | `NB_20_Silver_Transformacao` |
| Notebook de biblioteca | `NB_<Nome>` (sem número; só definições) | `NB_Utils` |
| Pipeline | `PL_<projeto>_<frequência>` | `PL_Marketing360_Diario` |
| Modelo semântico | `SM_<projeto>` | `SM_Marketing360` |
| Relatório | `RPT_<projeto>` | `RPT_Marketing360` |
| Ambiente | `ENV_<projeto>` | `ENV_Marketing360` |

## Nomes de dados
- Tabelas e colunas em `snake_case`, português, sem acentos: `fact_conversoes`, `valor_contratado`.
- Gold: `dim_*`, `fact_*`. Chaves substitutas `sk_*` e de negócio `id_*`. Flags booleanas como nomes (`tem_app`).
- Colunas técnicas começam por `_`: `_id_lote`, `_data_ingestao`, `_hash_linha`.
- Tabelas operacionais: `ops_*` (Lakehouse) e esquema `ctl` (Warehouse).
- No modelo semântico: tabelas com nomes de negócio (`Cliente`, `Conversões`) e medidas em Title Case com pastas numeradas.

## Código
- Python: `ruff` (estilo + imports), funções pequenas com *docstring*, sem lógica em `NB_Config`.
- Regras de negócio **só** em `NB_Transformacoes` (funções puras); cada regra nova tem um teste.
- Nada de credenciais, IDs ou caminhos fixos no código: tudo por nome a partir de `NB_Config`.
- T-SQL: palavras reservadas em maiúsculas, um procedimento por objeto, `TRY/CATCH` + transação + log, scripts reexecutáveis (`CREATE OR ALTER`, `IF … IS NULL`).
- DAX: `DIVIDE` em vez de `/`, variáveis (`VAR`) em medidas longas, formato e descrição em todas as medidas.

## Git
- Ramos: `main` (= PRD), `develop` (= DEV), `feature/<descrição>` por alteração.
- *Pull request* obrigatório para `main`, com CI verde e uma revisão.
- Mensagens: `tipo(âmbito): descrição` — ex.: `feat(silver): regra de validação de NIF`.
- Os ficheiros em `fabric/` são geridos pela integração Git do Fabric e não se editam à mão.

## Checklist de revisão (PR)
- [ ] Testes novos/atualizados e `pytest` verde
- [ ] Regras de qualidade para colunas novas
- [ ] Dicionário de dados atualizado (`docs/04`)
- [ ] Scripts SQL reexecutáveis
- [ ] Medidas com formato, pasta e descrição
- [ ] Nenhum dado pessoal real em código, testes ou exemplos
