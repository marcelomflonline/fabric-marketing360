/* =====================================================================================
   WH_00 — Esquemas, controlo e funções (roles)               Warehouse: WH_Gold
   Ordem de execução: WH_00 → WH_01 → WH_02 → WH_03 → WH_04 → WH_05 → WH_06 → (WH_07 testes)
   Todos os scripts são reexecutáveis (idempotentes).
   ===================================================================================== */

IF SCHEMA_ID('gold')      IS NULL EXEC('CREATE SCHEMA gold');       -- modelo dimensional (consumo)
IF SCHEMA_ID('ctl')       IS NULL EXEC('CREATE SCHEMA ctl');        -- controlo, watermarks, logs
IF SCHEMA_ID('seguranca') IS NULL EXEC('CREATE SCHEMA seguranca');  -- tabelas de acesso
GO

/* ---------- Watermarks: até onde a Gold já leu cada tabela Silver ---------- */
IF OBJECT_ID('ctl.watermark') IS NULL
CREATE TABLE ctl.watermark (
    tabela_destino     VARCHAR(100)  NOT NULL,
    valor              DATETIME2(6)  NOT NULL,
    data_atualizacao   DATETIME2(3)  NOT NULL
);
GO

INSERT INTO ctl.watermark (tabela_destino, valor, data_atualizacao)
SELECT v.t, '1900-01-01', SYSUTCDATETIME()
FROM (VALUES ('gold.dim_cliente'), ('gold.fact_contactos'), ('gold.fact_conversoes'),
             ('gold.fact_custos_campanha')) AS v(t)
WHERE NOT EXISTS (SELECT 1 FROM ctl.watermark w WHERE w.tabela_destino = v.t);
GO

/* ---------- Log de execução ---------- */
IF OBJECT_ID('ctl.log_execucao') IS NULL
CREATE TABLE ctl.log_execucao (
    id_lote        VARCHAR(100)   NOT NULL,
    objeto         VARCHAR(100)   NOT NULL,
    estado         VARCHAR(10)    NOT NULL,     -- INICIO | OK | ERRO
    linhas         BIGINT         NULL,
    mensagem       VARCHAR(4000)  NULL,
    inicio         DATETIME2(3)   NOT NULL,
    fim            DATETIME2(3)   NULL,
    duracao_seg    INT            NULL
);
GO

CREATE OR ALTER PROCEDURE ctl.usp_registar_log
    @id_lote VARCHAR(100), @objeto VARCHAR(100), @estado VARCHAR(10),
    @linhas BIGINT = NULL, @mensagem VARCHAR(4000) = NULL, @inicio DATETIME2(3) = NULL
AS
BEGIN
    DECLARE @agora DATETIME2(3) = SYSUTCDATETIME();
    INSERT INTO ctl.log_execucao (id_lote, objeto, estado, linhas, mensagem, inicio, fim, duracao_seg)
    VALUES (@id_lote, @objeto, @estado, @linhas, @mensagem, COALESCE(@inicio, @agora), @agora,
            DATEDIFF(SECOND, COALESCE(@inicio, @agora), @agora));
END;
GO

CREATE OR ALTER PROCEDURE ctl.usp_atualizar_watermark
    @tabela_destino VARCHAR(100), @valor DATETIME2(6)
AS
BEGIN
    IF @valor IS NULL RETURN;
    UPDATE ctl.watermark
       SET valor = @valor, data_atualizacao = SYSUTCDATETIME()
     WHERE tabela_destino = @tabela_destino;
END;
GO

/* ---------- Funções (roles) de base de dados: privilégio mínimo ----------
   Atribuir utilizadores/grupos Entra ID às roles em vez de dar permissões diretas. */
IF DATABASE_PRINCIPAL_ID('rl_marketing_leitura') IS NULL CREATE ROLE rl_marketing_leitura;
IF DATABASE_PRINCIPAL_ID('rl_engenharia_dados')  IS NULL CREATE ROLE rl_engenharia_dados;
GO
GRANT SELECT ON SCHEMA::gold TO rl_marketing_leitura;
GRANT SELECT, INSERT, UPDATE, DELETE, EXECUTE ON SCHEMA::gold TO rl_engenharia_dados;
GRANT SELECT, INSERT, UPDATE, DELETE, EXECUTE ON SCHEMA::ctl  TO rl_engenharia_dados;
-- Exemplo: ALTER ROLE rl_marketing_leitura ADD MEMBER [grupo-marketing@empresa.pt];
GO
