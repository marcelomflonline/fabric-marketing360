# 05 — CI/CD e ambientes

## Ambientes
| Ambiente | Workspace | Ramo Git | Quem altera |
|---|---|---|---|
| DEV | `WS_Marketing360_DEV` | `develop` (sincronizado pela integração Git) | Engenharia de dados |
| PRD | `WS_Marketing360_PRD` | `main` (publicado por CI/CD ou *deployment pipeline*) | Ninguém diretamente |

Ambos podem usar a capacidade trial. Os itens têm **os mesmos nomes** nos dois workspaces e o código resolve-os
por nome, por isso não há caminhos a trocar entre ambientes.

## Opção A — Deployment pipelines (sem código, recomendado no trial)
1. **Pipelines de implementação → Novo** → etapas *Desenvolvimento* e *Produção* → atribuir os workspaces.
2. Implementar de DEV → PRD (seleciona itens, mostra as diferenças).
3. Depois da 1.ª implementação: executar `WH_00…WH_06` no `WH_Gold` de PRD (o *schema* do Warehouse
   também é implementado, mas os dados não), a carga inicial e o `NB_40`.

## Opção B — Git + GitHub Actions + fabric-cicd (padrão de mercado)
1. **DEV → Definições do workspace → Integração Git** → GitHub/Azure DevOps, ramo `develop`, pasta `fabric`.
   O Fabric serializa cada item (notebooks `.py`, modelo em TMDL, relatório em PBIR, Warehouse em projeto SQL).
2. Fluxo de trabalho: `feature/*` → PR para `develop` → **CI** (`ci.yml`: ruff + pytest + simulação) → *merge* →
   o workspace DEV faz *Update all* → testes no DEV → PR `develop` → `main`.
3. **CD** (`deploy.yml`): no *push* para `main`, depois de aprovação no *GitHub Environment* `producao`,
   `cicd/deploy.py` publica em PRD com `fabric-cicd` e remove itens órfãos.
4. Secrets: `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `FABRIC_WS_PRD`.
   O *service principal* precisa de ser **Contributor** em PRD e o tenant tem de permitir
   *Service principals can use Fabric APIs*. Num tenant trial empresarial isto depende do administrador.
   Se não for possível, usar a Opção A.

## O que fica fora do Git
- Dados (Delta, ficheiros) e conteúdo de tabelas do Warehouse.
- Ligações e credenciais: configuradas por ambiente no portal.
- Acessos (roles do workspace, membros da role RLS, `gold.rls_acesso_regiao`): geridos por ambiente.

## Ordem de implementação num ambiente novo
1. Lakehouses e Warehouse (vazios) → 2. scripts `WH_00…WH_06` → 3. notebooks e pipelines →
4. carga inicial (`NB_00` com `p_gerar_dados="inicial"` em DEV; em PRD, a fonte real) → `ctl.usp_carregar_gold` →
5. modelo semântico + `NB_40` → 6. relatório e App → 7. ativar agendamentos.
