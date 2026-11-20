/* =====================================================================================
   WH_04 — Orquestração da Gold e testes de qualidade automáticos    Warehouse: WH_Gold
   Chamado pelo pipeline (atividade "Procedimento armazenado"):
       EXEC ctl.usp_carregar_gold @id_lote = '<RunId do pipeline>';
   ===================================================================================== */

/* ---------- Testes de qualidade da Gold ----------
   Cada teste devolve o nº de falhas. Severidade 'BLOQUEANTE' faz o procedimento falhar
   (e o pipeline alertar); 'AVISO' só fica registado. Resultados em ctl.resultado_testes. */
IF OBJECT_ID('ctl.resultado_testes') IS NULL
CREATE TABLE ctl.resultado_testes (
    id_lote     VARCHAR(100)  NOT NULL,
    teste       VARCHAR(200)  NOT NULL,
    severidade  VARCHAR(12)   NOT NULL,
    falhas      BIGINT        NOT NULL,
    data_teste  DATETIME2(3)  NOT NULL
);
GO

CREATE OR ALTER PROCEDURE ctl.usp_testes_qualidade_gold @id_lote VARCHAR(100)
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @agora DATETIME2(3) = SYSUTCDATETIME(), @bloqueantes BIGINT, @msg VARCHAR(4000);

    INSERT INTO ctl.resultado_testes (id_lote, teste, severidade, falhas, data_teste)
    SELECT @id_lote, teste, severidade, falhas, @agora FROM (
        -- Unicidade
        SELECT 'fact_contactos: id_contacto duplicado' AS teste, 'BLOQUEANTE' AS severidade,
               (SELECT COUNT(*) FROM (SELECT id_contacto FROM gold.fact_contactos GROUP BY id_contacto HAVING COUNT(*) > 1) x) AS falhas
        UNION ALL
        SELECT 'fact_conversoes: id_conversao duplicado', 'BLOQUEANTE',
               (SELECT COUNT(*) FROM (SELECT id_conversao FROM gold.fact_conversoes GROUP BY id_conversao HAVING COUNT(*) > 1) x)
        UNION ALL
        SELECT 'dim_cliente: mais de uma versão atual por cliente', 'BLOQUEANTE',
               (SELECT COUNT(*) FROM (SELECT id_cliente FROM gold.dim_cliente WHERE registo_atual = 1 GROUP BY id_cliente HAVING COUNT(*) > 1) x)
        UNION ALL
        SELECT 'dim_cliente: versões sobrepostas no tempo', 'BLOQUEANTE',
               (SELECT COUNT(*) FROM gold.dim_cliente a JOIN gold.dim_cliente b
                  ON a.id_cliente = b.id_cliente AND a.sk_cliente < b.sk_cliente
                 AND a.valido_de <= b.valido_ate AND b.valido_de <= a.valido_ate)
        UNION ALL
        -- Integridade referencial
        SELECT 'fact_contactos: data inexistente em dim_data', 'BLOQUEANTE',
               (SELECT COUNT(*) FROM gold.fact_contactos f WHERE NOT EXISTS (SELECT 1 FROM gold.dim_data d WHERE d.id_data = f.id_data_envio))
        UNION ALL
        SELECT 'fact_conversoes: data inexistente em dim_data', 'BLOQUEANTE',
               (SELECT COUNT(*) FROM gold.fact_conversoes f WHERE NOT EXISTS (SELECT 1 FROM gold.dim_data d WHERE d.id_data = f.id_data_conversao))
        UNION ALL
        SELECT 'fact_contactos: associado a cliente desconhecido', 'AVISO',
               (SELECT COUNT(*) FROM gold.fact_contactos f JOIN gold.dim_cliente d ON d.sk_cliente = f.sk_cliente WHERE d.id_cliente = -1)
        UNION ALL
        SELECT 'fact_conversoes: associada a campanha desconhecida', 'AVISO',
               (SELECT COUNT(*) FROM gold.fact_conversoes f JOIN gold.dim_campanha d ON d.sk_campanha = f.sk_campanha WHERE d.id_campanha = '-1')
        UNION ALL
        -- Regras de negócio
        SELECT 'funil incoerente (clique sem abertura ou abertura sem entrega)', 'BLOQUEANTE',
               (SELECT COUNT(*) FROM gold.fact_contactos WHERE clicado > aberto OR aberto > entregue)
        UNION ALL
        SELECT 'valores contratados negativos', 'BLOQUEANTE',
               (SELECT COUNT(*) FROM gold.fact_conversoes WHERE valor_contratado < 0)
        UNION ALL
        SELECT 'RGPD: contactos a clientes sem consentimento (na data do envio)', 'AVISO',
               (SELECT COUNT(*) FROM gold.fact_contactos f JOIN gold.dim_cliente d ON d.sk_cliente = f.sk_cliente
                 WHERE d.consentimento_marketing = 0 AND d.id_cliente <> -1)
        UNION ALL
        -- Reconciliação com a Silver
        SELECT 'reconciliação: nº de contactos Silver ≠ Gold', 'BLOQUEANTE',
               ABS((SELECT COUNT_BIG(*) FROM LH_Silver.dbo.contactos) - (SELECT COUNT_BIG(*) FROM gold.fact_contactos))
        UNION ALL
        SELECT 'reconciliação: valor contratado Silver ≠ Gold (€)', 'BLOQUEANTE',
               CAST(ABS(COALESCE((SELECT SUM(valor_contratado) FROM LH_Silver.dbo.conversoes), 0)
                      - COALESCE((SELECT SUM(valor_contratado) FROM gold.fact_conversoes), 0)) AS BIGINT)
    ) AS t;

    SELECT @bloqueantes = COUNT(*) FROM ctl.resultado_testes
     WHERE id_lote = @id_lote AND data_teste = @agora AND severidade = 'BLOQUEANTE' AND falhas > 0;

    SELECT teste, severidade, falhas FROM ctl.resultado_testes
     WHERE id_lote = @id_lote AND data_teste = @agora ORDER BY severidade, falhas DESC;

    IF @bloqueantes > 0
    BEGIN
        SET @msg = CONCAT(@bloqueantes, ' teste(s) bloqueante(s) falharam. Ver ctl.resultado_testes, id_lote=', @id_lote);
        EXEC ctl.usp_registar_log @id_lote, 'ctl.testes_qualidade', 'ERRO', @bloqueantes, @msg, @agora;
        THROW 50001, @msg, 1;
    END
    EXEC ctl.usp_registar_log @id_lote, 'ctl.testes_qualidade', 'OK', 0, NULL, @agora;
END;
GO

/* ---------- Orquestrador da Gold ----------
   Ordem: dimensões → factos → snapshot → testes. Cada passo tem a sua transação, por isso um
   erro num facto não desfaz as dimensões já carregadas (e a reexecução retoma pelo watermark). */
CREATE OR ALTER PROCEDURE ctl.usp_carregar_gold
    @id_lote VARCHAR(100) = NULL,
    @executar_testes BIT = 1
AS
BEGIN
    SET NOCOUNT ON;
    SET @id_lote = COALESCE(@id_lote, CONCAT('manual_', CONVERT(VARCHAR(8), SYSUTCDATETIME(), 112), REPLACE(CONVERT(VARCHAR(8), SYSUTCDATETIME(), 108), ':', '')));
    DECLARE @inicio DATETIME2(3) = SYSUTCDATETIME(), @erro VARCHAR(4000);

    EXEC ctl.usp_registar_log @id_lote, 'ctl.usp_carregar_gold', 'INICIO', NULL, NULL, @inicio;
    BEGIN TRY
        EXEC gold.usp_carregar_dim_data            @id_lote;
        EXEC gold.usp_carregar_dim_produto         @id_lote;
        EXEC gold.usp_carregar_dim_campanha        @id_lote;
        EXEC gold.usp_carregar_dim_cliente         @id_lote;
        EXEC gold.usp_carregar_fact_contactos      @id_lote;
        EXEC gold.usp_carregar_fact_conversoes     @id_lote;
        EXEC gold.usp_carregar_fact_custos_campanha @id_lote;
        EXEC gold.usp_calcular_cliente_envolvimento @id_lote;
        IF @executar_testes = 1
            EXEC ctl.usp_testes_qualidade_gold @id_lote;
        EXEC ctl.usp_registar_log @id_lote, 'ctl.usp_carregar_gold', 'OK', NULL, NULL, @inicio;
    END TRY
    BEGIN CATCH
        SET @erro = ERROR_MESSAGE();
        EXEC ctl.usp_registar_log @id_lote, 'ctl.usp_carregar_gold', 'ERRO', NULL, @erro, @inicio;
        THROW;
    END CATCH
END;
GO
