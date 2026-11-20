/* =====================================================================================
   WH_05 — Vistas de consumo e de monitorização              Warehouse: WH_Gold
   ===================================================================================== */

/* ---------- KPIs por campanha (SQL ad hoc, exportações, Excel) ---------- */
CREATE OR ALTER VIEW gold.vw_kpi_campanha AS
WITH ct AS (
    SELECT sk_campanha, SUM(enviado) AS enviados, SUM(entregue) AS entregues,
           SUM(aberto) AS aberturas, SUM(clicado) AS cliques
    FROM gold.fact_contactos GROUP BY sk_campanha
), cv AS (
    SELECT sk_campanha, COUNT(*) AS conversoes, SUM(valor_contratado) AS valor_contratado,
           SUM(receita_estimada) AS receita_estimada
    FROM gold.fact_conversoes GROUP BY sk_campanha
), cs AS (
    SELECT sk_campanha, SUM(custo) AS custo, SUM(impressoes) AS impressoes
    FROM gold.fact_custos_campanha GROUP BY sk_campanha
)
SELECT c.id_campanha, c.nome_campanha, c.canal, c.tipo_canal, c.objetivo, c.segmento_alvo,
       c.produto_campanha, c.categoria_produto, c.data_inicio, c.data_fim, c.orcamento,
       COALESCE(ct.enviados, 0) AS enviados, COALESCE(ct.entregues, 0) AS entregues,
       COALESCE(ct.aberturas, 0) AS aberturas, COALESCE(ct.cliques, 0) AS cliques,
       COALESCE(cv.conversoes, 0) AS conversoes, COALESCE(cv.valor_contratado, 0) AS valor_contratado,
       COALESCE(cv.receita_estimada, 0) AS receita_estimada, COALESCE(cs.custo, 0) AS custo,
       CAST(1.0 * ct.aberturas  / NULLIF(ct.entregues, 0) AS DECIMAL(9,4))         AS taxa_abertura,
       CAST(1.0 * ct.cliques    / NULLIF(ct.entregues, 0) AS DECIMAL(9,4))         AS ctr,
       CAST(1.0 * cv.conversoes / NULLIF(ct.enviados, 0) AS DECIMAL(9,4))          AS taxa_conversao,
       CAST(cs.custo / NULLIF(cv.conversoes, 0) AS DECIMAL(18,2))                  AS cpa,
       CAST((cv.receita_estimada - cs.custo) / NULLIF(cs.custo, 0) AS DECIMAL(18,4)) AS roi,
       CAST(cs.custo / NULLIF(c.orcamento, 0) AS DECIMAL(9,4))                     AS execucao_orcamento
FROM gold.dim_campanha c
LEFT JOIN ct ON ct.sk_campanha = c.sk_campanha
LEFT JOIN cv ON cv.sk_campanha = c.sk_campanha
LEFT JOIN cs ON cs.sk_campanha = c.sk_campanha
WHERE c.id_campanha <> '-1';
GO

/* ---------- Histórico de alterações de clientes (SCD2) ---------- */
CREATE OR ALTER VIEW gold.vw_historico_cliente AS
SELECT id_cliente, sk_cliente, segmento, escalao_rendimento, distrito, regiao, consentimento_marketing,
       valido_de, valido_ate, registo_atual
FROM gold.dim_cliente
WHERE id_cliente IN (SELECT id_cliente FROM gold.dim_cliente GROUP BY id_cliente HAVING COUNT(*) > 1);
GO

/* ---------- Monitorização ponta-a-ponta (Lakehouse + Warehouse) ---------- */
CREATE OR ALTER VIEW ctl.vw_monitorizacao AS
SELECT 'Lakehouse' AS motor, camada, entidade AS objeto, id_lote, estado,
       CAST(inicio AS DATETIME2(3)) AS inicio, CAST(fim AS DATETIME2(3)) AS fim,
       CAST(duracao_seg AS INT) AS duracao_seg, CAST(LEFT(COALESCE(erro, metricas), 4000) AS VARCHAR(4000)) AS detalhe
FROM LH_Silver.dbo.ops_log_execucao
UNION ALL
SELECT 'Warehouse', 'gold', objeto, id_lote, estado, inicio, fim, duracao_seg, mensagem
FROM ctl.log_execucao;
GO

/* ---------- Quarentena por resolver ---------- */
CREATE OR ALTER VIEW ctl.vw_quarentena_pendente AS
SELECT entidade, regras_falhadas, COUNT(*) AS registos, MIN(data_quarentena) AS desde, MAX(id_lote) AS ultimo_lote
FROM LH_Silver.dbo.ops_quarentena
WHERE resolvido = 0
GROUP BY entidade, regras_falhadas;
GO
