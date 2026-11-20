/* =====================================================================================
   WH_02 — Carga das dimensões                                Warehouse: WH_Gold
   Fonte: SQL analytics endpoint do LH_Silver (mesmo workspace) → LH_Silver.dbo.<tabela>
   Cada procedimento: transação própria + TRY/CATCH + registo em ctl.log_execucao.
   ===================================================================================== */

/* ---------- dim_data: recarga total (tabela pequena e estática) ---------- */
CREATE OR ALTER PROCEDURE gold.usp_carregar_dim_data @id_lote VARCHAR(100)
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @inicio DATETIME2(3) = SYSUTCDATETIME(), @n BIGINT, @erro VARCHAR(4000);
    BEGIN TRY
        BEGIN TRANSACTION;
        DELETE FROM gold.dim_data;
        INSERT INTO gold.dim_data
        SELECT id_data, data, ano, trimestre, ano_trimestre, num_mes, mes, mes_abrev, ano_mes,
               semana_iso, dia_semana, num_dia_semana, CAST(fim_de_semana AS BIT)
        FROM LH_Silver.dbo.calendario;
        SET @n = @@ROWCOUNT;
        COMMIT;
        EXEC ctl.usp_registar_log @id_lote, 'gold.dim_data', 'OK', @n, NULL, @inicio;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK;
        SET @erro = ERROR_MESSAGE();
        EXEC ctl.usp_registar_log @id_lote, 'gold.dim_data', 'ERRO', NULL, @erro, @inicio;
        THROW;
    END CATCH
END;
GO

/* ---------- dim_produto: SCD tipo 1 com MERGE (só atualiza se o hash mudou) ---------- */
CREATE OR ALTER PROCEDURE gold.usp_carregar_dim_produto @id_lote VARCHAR(100)
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @inicio DATETIME2(3) = SYSUTCDATETIME(), @n BIGINT, @erro VARCHAR(4000);
    BEGIN TRY
        BEGIN TRANSACTION;
        MERGE INTO gold.dim_produto AS t
        USING (SELECT id_produto, nome_produto, categoria, margem_estimada, _hash_linha
               FROM LH_Silver.dbo.produtos) AS s
           ON t.id_produto = s.id_produto
        WHEN MATCHED AND (t.hash_origem IS NULL OR t.hash_origem <> s._hash_linha) THEN
            UPDATE SET nome_produto = s.nome_produto, categoria = s.categoria,
                       margem_estimada = s.margem_estimada, hash_origem = s._hash_linha,
                       data_atualizacao = @inicio
        WHEN NOT MATCHED THEN
            INSERT (id_produto, nome_produto, categoria, margem_estimada, hash_origem, data_criacao, data_atualizacao)
            VALUES (s.id_produto, s.nome_produto, s.categoria, s.margem_estimada, s._hash_linha, @inicio, @inicio);
        SET @n = @@ROWCOUNT;
        COMMIT;
        EXEC ctl.usp_registar_log @id_lote, 'gold.dim_produto', 'OK', @n, NULL, @inicio;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK;
        SET @erro = ERROR_MESSAGE();
        EXEC ctl.usp_registar_log @id_lote, 'gold.dim_produto', 'ERRO', NULL, @erro, @inicio;
        THROW;
    END CATCH
END;
GO

/* ---------- dim_campanha: SCD tipo 1 com MERGE ---------- */
CREATE OR ALTER PROCEDURE gold.usp_carregar_dim_campanha @id_lote VARCHAR(100)
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @inicio DATETIME2(3) = SYSUTCDATETIME(), @n BIGINT, @erro VARCHAR(4000);
    BEGIN TRY
        BEGIN TRANSACTION;
        MERGE INTO gold.dim_campanha AS t
        USING (
            SELECT c.id_campanha, c.nome_campanha, c.canal, c.tipo_canal,
                   COALESCE(c.objetivo, 'Desconhecido')      AS objetivo,
                   COALESCE(c.segmento_alvo, 'Desconhecido') AS segmento_alvo,
                   COALESCE(c.id_produto, -1)                AS id_produto,
                   COALESCE(p.nome_produto, 'Desconhecido')  AS produto_campanha,
                   COALESCE(p.categoria, 'Desconhecido')     AS categoria_produto,
                   c.data_inicio, c.data_fim, c.duracao_dias,
                   COALESCE(c.orcamento, 0) AS orcamento,
                   c._hash_linha
            FROM LH_Silver.dbo.campanhas AS c
            LEFT JOIN LH_Silver.dbo.produtos AS p ON p.id_produto = c.id_produto
        ) AS s
           ON t.id_campanha = s.id_campanha
        WHEN MATCHED AND (t.hash_origem IS NULL OR t.hash_origem <> s._hash_linha) THEN
            UPDATE SET nome_campanha = s.nome_campanha, canal = s.canal, tipo_canal = s.tipo_canal,
                       objetivo = s.objetivo, segmento_alvo = s.segmento_alvo, id_produto = s.id_produto,
                       produto_campanha = s.produto_campanha, categoria_produto = s.categoria_produto,
                       data_inicio = s.data_inicio, data_fim = s.data_fim, duracao_dias = s.duracao_dias,
                       orcamento = s.orcamento, hash_origem = s._hash_linha, data_atualizacao = @inicio
        WHEN NOT MATCHED THEN
            INSERT (id_campanha, nome_campanha, canal, tipo_canal, objetivo, segmento_alvo, id_produto,
                    produto_campanha, categoria_produto, data_inicio, data_fim, duracao_dias, orcamento,
                    hash_origem, data_criacao, data_atualizacao)
            VALUES (s.id_campanha, s.nome_campanha, s.canal, s.tipo_canal, s.objetivo, s.segmento_alvo, s.id_produto,
                    s.produto_campanha, s.categoria_produto, s.data_inicio, s.data_fim, s.duracao_dias, s.orcamento,
                    s._hash_linha, @inicio, @inicio);
        SET @n = @@ROWCOUNT;
        COMMIT;
        EXEC ctl.usp_registar_log @id_lote, 'gold.dim_campanha', 'OK', @n, NULL, @inicio;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK;
        SET @erro = ERROR_MESSAGE();
        EXEC ctl.usp_registar_log @id_lote, 'gold.dim_campanha', 'ERRO', NULL, @erro, @inicio;
        THROW;
    END CATCH
END;
GO

/* ---------- dim_cliente: SCD tipo 2 incremental ----------
   1) fecha a versão atual dos clientes cujos atributos tipo 2 mudaram (hash_scd2 diferente);
   2) insere nova versão para clientes novos ou com versão fechada no passo 1;
   3) sobrepõe atributos tipo 1 na versão atual.
   A data de validade vem da data de extração do ficheiro de origem (_data_extracao). */
CREATE OR ALTER PROCEDURE gold.usp_carregar_dim_cliente @id_lote VARCHAR(100)
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @inicio DATETIME2(3) = SYSUTCDATETIME(), @erro VARCHAR(4000);
    DECLARE @n_fechadas BIGINT = 0, @n_novas BIGINT = 0, @n_tipo1 BIGINT = 0, @msg VARCHAR(4000);
    DECLARE @wm DATETIME2(6)      = (SELECT valor FROM ctl.watermark WHERE tabela_destino = 'gold.dim_cliente');
    DECLARE @wm_novo DATETIME2(6) = (SELECT MAX(_data_processamento) FROM LH_Silver.dbo.clientes);

    BEGIN TRY
        BEGIN TRANSACTION;

        -- 1) Expirar versões alteradas
        UPDATE t
           SET valido_ate = CASE WHEN DATEADD(DAY, -1, COALESCE(s._data_extracao, CAST(@inicio AS DATE))) < t.valido_de
                                 THEN t.valido_de
                                 ELSE DATEADD(DAY, -1, COALESCE(s._data_extracao, CAST(@inicio AS DATE))) END,
               registo_atual = 0,
               data_atualizacao = @inicio
          FROM gold.dim_cliente AS t
          INNER JOIN LH_Silver.dbo.clientes AS s ON s.id_cliente = t.id_cliente
         WHERE t.registo_atual = 1
           AND t.hash_scd2 <> s.hash_scd2
           AND s._data_processamento > @wm AND s._data_processamento <= @wm_novo;
        SET @n_fechadas = @@ROWCOUNT;

        -- 2) Novas versões (clientes novos ou cuja versão atual acabou de ser fechada)
        INSERT INTO gold.dim_cliente (id_cliente, segmento, escalao_rendimento, distrito, regiao, consentimento_marketing,
                                      data_nascimento, idade, faixa_etaria, genero, canal_preferido, data_adesao,
                                      antiguidade_anos, escalao_antiguidade, tem_email, tem_app, hash_scd2, hash_scd1,
                                      valido_de, valido_ate, registo_atual, data_criacao, data_atualizacao)
        SELECT s.id_cliente, s.segmento, s.escalao_rendimento, s.distrito, s.regiao,
               CAST(s.consentimento_marketing AS BIT),
               s.data_nascimento, s.idade, s.faixa_etaria, s.genero, s.canal_preferido, s.data_adesao,
               s.antiguidade_anos,
               CASE WHEN s.antiguidade_anos < 2 THEN '0-1 anos' WHEN s.antiguidade_anos < 5 THEN '2-4 anos'
                    WHEN s.antiguidade_anos < 10 THEN '5-9 anos' ELSE '10+ anos' END,
               CAST(s.tem_email AS BIT), CAST(s.tem_app AS BIT), s.hash_scd2, s.hash_scd1,
               CASE WHEN EXISTS (SELECT 1 FROM gold.dim_cliente h WHERE h.id_cliente = s.id_cliente)
                    THEN COALESCE(s._data_extracao, CAST(@inicio AS DATE))
                    ELSE CAST('1900-01-01' AS DATE) END,          -- 1.ª versão cobre todo o histórico
               CAST('9999-12-31' AS DATE), 1, @inicio, @inicio
          FROM LH_Silver.dbo.clientes AS s
         WHERE s._data_processamento > @wm AND s._data_processamento <= @wm_novo
           AND NOT EXISTS (SELECT 1 FROM gold.dim_cliente t
                            WHERE t.id_cliente = s.id_cliente AND t.registo_atual = 1);
        SET @n_novas = @@ROWCOUNT;

        -- 3) Atributos tipo 1 na versão atual
        UPDATE t
           SET data_nascimento = s.data_nascimento, idade = s.idade, faixa_etaria = s.faixa_etaria,
               genero = s.genero, canal_preferido = s.canal_preferido, data_adesao = s.data_adesao,
               antiguidade_anos = s.antiguidade_anos,
               escalao_antiguidade = CASE WHEN s.antiguidade_anos < 2 THEN '0-1 anos' WHEN s.antiguidade_anos < 5 THEN '2-4 anos'
                                          WHEN s.antiguidade_anos < 10 THEN '5-9 anos' ELSE '10+ anos' END,
               tem_email = CAST(s.tem_email AS BIT), tem_app = CAST(s.tem_app AS BIT),
               hash_scd1 = s.hash_scd1, data_atualizacao = @inicio
          FROM gold.dim_cliente AS t
          INNER JOIN LH_Silver.dbo.clientes AS s ON s.id_cliente = t.id_cliente
         WHERE t.registo_atual = 1
           AND t.hash_scd2 = s.hash_scd2
           AND (t.hash_scd1 <> s.hash_scd1 OR t.idade <> s.idade OR t.antiguidade_anos <> s.antiguidade_anos)
           AND s._data_processamento > @wm AND s._data_processamento <= @wm_novo;
        SET @n_tipo1 = @@ROWCOUNT;

        EXEC ctl.usp_atualizar_watermark 'gold.dim_cliente', @wm_novo;
        COMMIT;

        SET @msg = CONCAT('versões fechadas=', @n_fechadas, '; versões novas=', @n_novas, '; atualizações tipo 1=', @n_tipo1);
        EXEC ctl.usp_registar_log @id_lote, 'gold.dim_cliente', 'OK', @n_novas, @msg, @inicio;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK;
        SET @erro = ERROR_MESSAGE();
        EXEC ctl.usp_registar_log @id_lote, 'gold.dim_cliente', 'ERRO', NULL, @erro, @inicio;
        THROW;
    END CATCH
END;
GO
