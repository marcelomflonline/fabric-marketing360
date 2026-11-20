# 03 — Runbook de operação

## Verificação diária (2 minutos)
```sql
-- No WH_Gold
SELECT TOP 50 * FROM ctl.vw_monitorizacao ORDER BY inicio DESC;          -- estado de cada passo
SELECT * FROM ctl.resultado_testes
 WHERE id_lote = (SELECT TOP 1 id_lote FROM ctl.log_execucao ORDER BY inicio DESC);  -- testes do último lote
SELECT * FROM ctl.vw_quarentena_pendente;                                 -- registos rejeitados por resolver
```
Também no portal: **Monitor** → execuções do pipeline `PL_Marketing360_Diario`.

## Falhas e o que fazer

| Sintoma | Causa provável | Ação |
|---|---|---|
| Passo `Lakehouse` falha numa entidade | ficheiro com formato inesperado ou erro de código | Ver `ops_log_execucao.erro` e o *snapshot* da atividade no DAG. Corrigir e **reexecutar o pipeline**: os ficheiros já ingeridos são ignorados e o watermark não avançou. |
| `Invalid object name 'LH_Silver.dbo.x'` na Gold | SQL endpoint ainda não sincronizou | Reexecutar o pipeline. Se persistir: no LH_Silver, abrir o SQL analytics endpoint e clicar em **Atualizar**. |
| Teste bloqueante falha (`THROW 50001`) | dados incoerentes chegaram à Gold | `SELECT * FROM ctl.resultado_testes WHERE falhas > 0`. As cargas já feitas ficam (transação por passo). Corrigir a origem e reprocessar. |
| Reconciliação Silver ≠ Gold | Gold não carregou parte da janela | `EXEC ctl.usp_carregar_gold` de novo (MERGE idempotente). Se necessário, recuar o watermark (abaixo). |
| Capacidade estrangulada (*throttling*) | trial partilhado, muitas execuções | Ver a app *Fabric Capacity Metrics*. Reduzir `p_concorrencia` no NB_00 e espaçar agendamentos. |
| Relatório sem dados novos | modelo não fez *reframing* | Executar a atualização do modelo `SM_Marketing360`. |

## Reprocessamentos
**Reprocessar a Silver de uma entidade a partir da Bronze** (ex.: depois de corrigir uma regra):
`NB_20_Silver_Transformacao` com `p_entidade = "clientes"` e `p_reprocessar = True`. O MERGE garante que não duplica.

**Recarregar um facto na Gold desde o início:**
```sql
UPDATE ctl.watermark SET valor = '1900-01-01' WHERE tabela_destino = 'gold.fact_conversoes';
EXEC ctl.usp_carregar_gold;
```

**Reingerir um ficheiro** (ex.: a origem reenviou-o corrigido com o mesmo nome):
1. Apagar o registo: `DELETE FROM ops_ficheiros_processados WHERE nome_ficheiro = '…'`
   (Spark SQL no LH_Silver, ou `DeltaTable.delete`).
2. Colocar o ficheiro em `Files/landing/<entidade>/` e reexecutar.

## Quarentena
1. `ctl.vw_quarentena_pendente` mostra o que falhou e porquê. A coluna `registo` de `ops_quarentena` tem a linha original em JSON.
2. Corrigir **na origem** e reenviar (preferível) ou, se o erro era da regra, corrigir a regra e reprocessar.
3. Marcar como resolvido:
```python
DeltaTable.forPath(spark, caminho_tabela(LH_SILVER, OPS_QUARENTENA)) \
    .update("entidade = 'contactos' AND chave = 'CT00001234X'", {"resolvido": "true"})
```

## Recuperar de um erro (time travel Delta, até 7 dias)
```sql
-- Spark SQL: ver versões e repor
DESCRIBE HISTORY delta.`abfss://…/LH_Silver…/Tables/dbo/clientes`;
RESTORE TABLE delta.`abfss://…/Tables/dbo/clientes` TO VERSION AS OF 42;
```
No Warehouse: *time travel* com `OPTION (FOR TIMESTAMP AS OF '2025-12-01T06:00:00')` em consultas, e *restore points* no portal.

## Antes do fim do trial (dia 50)
- Confirmar que o repositório Git tem a última versão de todos os itens.
- Exportar o relatório (PDF/PowerPoint) e guardar `ctl.resultado_testes` e as métricas se forem precisas.
- Para continuar: atribuir o workspace a uma capacidade F paga (os dados ficam 7 dias após o fim do trial).
