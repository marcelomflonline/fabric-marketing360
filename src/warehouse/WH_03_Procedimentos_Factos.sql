/* =====================================================================================
   WH_03 — Carga incremental dos factos                       Warehouse: WH_Gold
   Padrão: janela de watermark ]wm, wm_novo] sobre Silver._data_processamento + MERGE por chave.
   - Reexecutar é seguro (MERGE); falhas não avançam o watermark (transação).
   - Lookup das dimensões com membro "Desconhecido" por omissão.
   - dim_cliente é procurada pela versão VÁLIDA NA DATA do evento (point-in-time, SCD2).
   ===================================================================================== */

/* ---------- fact_contactos ---------- */
CREATE OR ALTER PROCEDURE gold.usp_carregar_fact_contactos @id_lote VARCHAR(100)
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @inicio DATETIME2(3) = SYSUTCDATETIME(), @n BIGINT, @erro VARCHAR(4000);
    DECLARE @wm DATETIME2(6)      = (SELECT valor FROM ctl.watermark WHERE tabela_destino = 'gold.fact_contactos');
    DECLARE @wm_novo DATETIME2(6) = (SELECT MAX(_data_processamento) FROM LH_Silver.dbo.contactos);
    DECLARE @sk_camp_desc BIGINT  = (SELECT MIN(sk_campanha) FROM gold.dim_campanha WHERE id_campanha = '-1');
    DECLARE @sk_cli_desc BIGINT   = (SELECT MIN(sk_cliente)  FROM gold.dim_cliente  WHERE id_cliente = -1);
    BEGIN TRY
        BEGIN TRANSACTION;
        MERGE INTO gold.fact_contactos AS t
        USING (
            SELECT s.id_contacto,
                   COALESCE(c.sk_campanha, @sk_camp_desc) AS sk_campanha,
                   COALESCE(d.sk_cliente, @sk_cli_desc)   AS sk_cliente,
                   YEAR(s.data_envio) * 10000 + MONTH(s.data_envio) * 100 + DAY(s.data_envio) AS id_data_envio,
                   s.hora_envio, s.flag_entregue, s.flag_aberto, s.flag_clicado
            FROM LH_Silver.dbo.contactos AS s
            LEFT JOIN gold.dim_campanha AS c ON c.id_campanha = s.id_campanha
            LEFT JOIN gold.dim_cliente  AS d ON d.id_cliente = s.id_cliente
                                            AND s.data_envio BETWEEN d.valido_de AND d.valido_ate
            WHERE s._data_processamento > @wm AND s._data_processamento <= @wm_novo
        ) AS s
           ON t.id_contacto = s.id_contacto
        WHEN MATCHED THEN
            UPDATE SET sk_campanha = s.sk_campanha, sk_cliente = s.sk_cliente, id_data_envio = s.id_data_envio,
                       hora_envio = s.hora_envio, entregue = s.flag_entregue, aberto = s.flag_aberto,
                       clicado = s.flag_clicado, id_lote = @id_lote, data_carga = @inicio
        WHEN NOT MATCHED THEN
            INSERT (id_contacto, sk_campanha, sk_cliente, id_data_envio, hora_envio, enviado, entregue, aberto,
                    clicado, convertido, id_lote, data_carga)
            VALUES (s.id_contacto, s.sk_campanha, s.sk_cliente, s.id_data_envio, s.hora_envio, 1, s.flag_entregue,
                    s.flag_aberto, s.flag_clicado, 0, @id_lote, @inicio);
        SET @n = @@ROWCOUNT;
        EXEC ctl.usp_atualizar_watermark 'gold.fact_contactos', @wm_novo;
        COMMIT;
        EXEC ctl.usp_registar_log @id_lote, 'gold.fact_contactos', 'OK', @n, NULL, @inicio;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK;
        SET @erro = ERROR_MESSAGE();
        EXEC ctl.usp_registar_log @id_lote, 'gold.fact_contactos', 'ERRO', NULL, @erro, @inicio;
        THROW;
    END CATCH
END;
GO

/* ---------- fact_conversoes ---------- */
CREATE OR ALTER PROCEDURE gold.usp_carregar_fact_conversoes @id_lote VARCHAR(100)
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @inicio DATETIME2(3) = SYSUTCDATETIME(), @n BIGINT, @erro VARCHAR(4000);
    DECLARE @wm DATETIME2(6)      = (SELECT valor FROM ctl.watermark WHERE tabela_destino = 'gold.fact_conversoes');
    DECLARE @wm_novo DATETIME2(6) = (SELECT MAX(_data_processamento) FROM LH_Silver.dbo.conversoes);
    DECLARE @sk_camp_desc BIGINT  = (SELECT MIN(sk_campanha) FROM gold.dim_campanha WHERE id_campanha = '-1');
    DECLARE @sk_cli_desc BIGINT   = (SELECT MIN(sk_cliente)  FROM gold.dim_cliente  WHERE id_cliente = -1);
    DECLARE @sk_prod_desc BIGINT  = (SELECT MIN(sk_produto)  FROM gold.dim_produto  WHERE id_produto = -1);
    BEGIN TRY
        BEGIN TRANSACTION;
        MERGE INTO gold.fact_conversoes AS t
        USING (
            SELECT s.id_conversao, s.id_contacto,
                   COALESCE(c.sk_campanha, @sk_camp_desc) AS sk_campanha,
                   COALESCE(d.sk_cliente, @sk_cli_desc)   AS sk_cliente,
                   COALESCE(p.sk_produto, @sk_prod_desc)  AS sk_produto,
                   YEAR(s.data_conversao) * 10000 + MONTH(s.data_conversao) * 100 + DAY(s.data_conversao) AS id_data_conversao,
                   s.canal_conversao,
                   CASE WHEN ct.flag_clicado = 1 THEN 'Clique' ELSE 'Janela 30 dias' END AS tipo_atribuicao,
                   DATEDIFF(DAY, ct.data_envio, s.data_conversao) AS dias_ate_conversao,
                   s.valor_contratado,
                   CAST(s.valor_contratado * COALESCE(p.margem_estimada, 0) AS DECIMAL(18,2)) AS receita_estimada
            FROM LH_Silver.dbo.conversoes AS s
            LEFT JOIN LH_Silver.dbo.contactos AS ct ON ct.id_contacto = s.id_contacto
            LEFT JOIN gold.dim_campanha AS c ON c.id_campanha = s.id_campanha
            LEFT JOIN gold.dim_produto  AS p ON p.id_produto = s.id_produto
            LEFT JOIN gold.dim_cliente  AS d ON d.id_cliente = s.id_cliente
                                            AND s.data_conversao BETWEEN d.valido_de AND d.valido_ate
            WHERE s._data_processamento > @wm AND s._data_processamento <= @wm_novo
        ) AS s
           ON t.id_conversao = s.id_conversao
        WHEN MATCHED THEN
            UPDATE SET id_contacto = s.id_contacto, sk_campanha = s.sk_campanha, sk_cliente = s.sk_cliente,
                       sk_produto = s.sk_produto, id_data_conversao = s.id_data_conversao,
                       canal_conversao = s.canal_conversao, tipo_atribuicao = s.tipo_atribuicao,
                       dias_ate_conversao = s.dias_ate_conversao, valor_contratado = s.valor_contratado,
                       receita_estimada = s.receita_estimada, id_lote = @id_lote, data_carga = @inicio
        WHEN NOT MATCHED THEN
            INSERT (id_conversao, id_contacto, sk_campanha, sk_cliente, sk_produto, id_data_conversao, canal_conversao,
                    tipo_atribuicao, dias_ate_conversao, valor_contratado, receita_estimada, id_lote, data_carga)
            VALUES (s.id_conversao, s.id_contacto, s.sk_campanha, s.sk_cliente, s.sk_produto, s.id_data_conversao,
                    s.canal_conversao, s.tipo_atribuicao, s.dias_ate_conversao, s.valor_contratado,
                    s.receita_estimada, @id_lote, @inicio);
        SET @n = @@ROWCOUNT;

        -- Conversões que chegam depois do contacto (late arriving): marcar o contacto como convertido
        UPDATE gold.fact_contactos
           SET convertido = 1, data_carga = @inicio
         WHERE convertido = 0
           AND id_contacto IN (SELECT id_contacto FROM gold.fact_conversoes WHERE id_contacto IS NOT NULL);

        EXEC ctl.usp_atualizar_watermark 'gold.fact_conversoes', @wm_novo;
        COMMIT;
        EXEC ctl.usp_registar_log @id_lote, 'gold.fact_conversoes', 'OK', @n, NULL, @inicio;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK;
        SET @erro = ERROR_MESSAGE();
        EXEC ctl.usp_registar_log @id_lote, 'gold.fact_conversoes', 'ERRO', NULL, @erro, @inicio;
        THROW;
    END CATCH
END;
GO

/* ---------- fact_custos_campanha ---------- */
CREATE OR ALTER PROCEDURE gold.usp_carregar_fact_custos_campanha @id_lote VARCHAR(100)
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @inicio DATETIME2(3) = SYSUTCDATETIME(), @n BIGINT, @erro VARCHAR(4000);
    DECLARE @wm DATETIME2(6)      = (SELECT valor FROM ctl.watermark WHERE tabela_destino = 'gold.fact_custos_campanha');
    DECLARE @wm_novo DATETIME2(6) = (SELECT MAX(_data_processamento) FROM LH_Silver.dbo.custos_campanha);
    DECLARE @sk_camp_desc BIGINT  = (SELECT MIN(sk_campanha) FROM gold.dim_campanha WHERE id_campanha = '-1');
    BEGIN TRY
        BEGIN TRANSACTION;
        MERGE INTO gold.fact_custos_campanha AS t
        USING (
            SELECT s.id_campanha,
                   COALESCE(c.sk_campanha, @sk_camp_desc) AS sk_campanha,
                   YEAR(s.data) * 10000 + MONTH(s.data) * 100 + DAY(s.data) AS id_data,
                   s.custo, s.impressoes
            FROM LH_Silver.dbo.custos_campanha AS s
            LEFT JOIN gold.dim_campanha AS c ON c.id_campanha = s.id_campanha
            WHERE s._data_processamento > @wm AND s._data_processamento <= @wm_novo
        ) AS s
           ON t.id_campanha = s.id_campanha AND t.id_data = s.id_data
        WHEN MATCHED THEN
            UPDATE SET sk_campanha = s.sk_campanha, custo = s.custo, impressoes = s.impressoes,
                       id_lote = @id_lote, data_carga = @inicio
        WHEN NOT MATCHED THEN
            INSERT (id_campanha, sk_campanha, id_data, custo, impressoes, id_lote, data_carga)
            VALUES (s.id_campanha, s.sk_campanha, s.id_data, s.custo, s.impressoes, @id_lote, @inicio);
        SET @n = @@ROWCOUNT;
        EXEC ctl.usp_atualizar_watermark 'gold.fact_custos_campanha', @wm_novo;
        COMMIT;
        EXEC ctl.usp_registar_log @id_lote, 'gold.fact_custos_campanha', 'OK', @n, NULL, @inicio;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK;
        SET @erro = ERROR_MESSAGE();
        EXEC ctl.usp_registar_log @id_lote, 'gold.fact_custos_campanha', 'ERRO', NULL, @erro, @inicio;
        THROW;
    END CATCH
END;
GO

/* ---------- cliente_envolvimento: snapshot recalculado a cada carga ----------
   Score 0-100 = abertura (até 30) + cliques (25 ou 40) + conversão (30), sobre todo o histórico
   do cliente (todas as versões SCD2), associado à versão atual. */
CREATE OR ALTER PROCEDURE gold.usp_calcular_cliente_envolvimento @id_lote VARCHAR(100)
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @inicio DATETIME2(3) = SYSUTCDATETIME(), @n BIGINT, @erro VARCHAR(4000);
    DECLARE @data_ref DATE = (SELECT MAX(d.data) FROM gold.fact_contactos f
                              JOIN gold.dim_data d ON d.id_data = f.id_data_envio);
    BEGIN TRY
        BEGIN TRANSACTION;
        DELETE FROM gold.cliente_envolvimento;

        WITH atual AS (
            SELECT sk_cliente, id_cliente FROM gold.dim_cliente WHERE registo_atual = 1 AND id_cliente <> -1
        ), ct AS (
            SELECT d.id_cliente, COUNT(*) AS n_contactos, SUM(f.aberto) AS n_aberturas, SUM(f.clicado) AS n_cliques,
                   MAX(CASE WHEN f.clicado = 1 THEN f.id_data_envio END) AS ultimo_clique
            FROM gold.fact_contactos f JOIN gold.dim_cliente d ON d.sk_cliente = f.sk_cliente
            GROUP BY d.id_cliente
        ), cv AS (
            SELECT d.id_cliente, COUNT(*) AS n_conversoes, SUM(f.valor_contratado) AS valor
            FROM gold.fact_conversoes f JOIN gold.dim_cliente d ON d.sk_cliente = f.sk_cliente
            GROUP BY d.id_cliente
        ), base AS (
            SELECT a.sk_cliente, a.id_cliente,
                   COALESCE(ct.n_contactos, 0) AS n_contactos, COALESCE(ct.n_aberturas, 0) AS n_aberturas,
                   COALESCE(ct.n_cliques, 0) AS n_cliques, COALESCE(cv.n_conversoes, 0) AS n_conversoes,
                   COALESCE(cv.valor, 0) AS valor,
                   DATEDIFF(DAY, CONVERT(DATE, CONVERT(VARCHAR(8), ct.ultimo_clique), 112), @data_ref) AS dias_clique
            FROM atual a
            LEFT JOIN ct ON ct.id_cliente = a.id_cliente
            LEFT JOIN cv ON cv.id_cliente = a.id_cliente
        ), score AS (
            SELECT *, CAST(
                      CASE WHEN n_contactos = 0 THEN 0 ELSE 30.0 * n_aberturas / n_contactos END
                    + CASE WHEN n_cliques >= 2 THEN 40 WHEN n_cliques = 1 THEN 25 ELSE 0 END
                    + CASE WHEN n_conversoes >= 1 THEN 30 ELSE 0 END AS INT) AS score
            FROM base
        )
        INSERT INTO gold.cliente_envolvimento
        SELECT sk_cliente, id_cliente, n_contactos, n_aberturas, n_cliques, n_conversoes, valor, dias_clique, score,
               CASE WHEN n_contactos = 0 THEN 'Inativo' WHEN score >= 55 THEN 'Alto'
                    WHEN score >= 25 THEN 'Médio' ELSE 'Baixo' END,
               @inicio
        FROM score;
        SET @n = @@ROWCOUNT;
        COMMIT;
        EXEC ctl.usp_registar_log @id_lote, 'gold.cliente_envolvimento', 'OK', @n, NULL, @inicio;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK;
        SET @erro = ERROR_MESSAGE();
        EXEC ctl.usp_registar_log @id_lote, 'gold.cliente_envolvimento', 'ERRO', NULL, @erro, @inicio;
        THROW;
    END CATCH
END;
GO
