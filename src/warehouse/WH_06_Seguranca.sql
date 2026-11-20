/* =====================================================================================
   WH_06 — Segurança dos dados de clientes                    Warehouse: WH_Gold
   Camadas de proteção (defesa em profundidade):
   1. Workspace: só Admin/Member para a equipa de dados; consumidores NÃO entram no workspace,
      recebem o relatório por App (ou partilha) → não veem Lakehouse/Warehouse.
   2. Warehouse: roles de base de dados (WH_00) e máscara dinâmica (abaixo).
   3. Modelo semântico: RLS por região (NB_40) e OLS opcional.
   4. Etiquetas de sensibilidade (Purview) no modelo e no relatório: "Confidencial".
   ===================================================================================== */

/* ---------- Máscara dinâmica: data de nascimento ----------
   Quem não tem UNMASK vê 1900-01-01; idade e faixa etária continuam disponíveis para análise. */
IF NOT EXISTS (SELECT 1 FROM sys.masked_columns WHERE object_id = OBJECT_ID('gold.dim_cliente') AND name = 'data_nascimento')
    ALTER TABLE gold.dim_cliente ALTER COLUMN data_nascimento ADD MASKED WITH (FUNCTION = 'default()');
GO
GRANT UNMASK TO rl_engenharia_dados;
GO

/* ---------- Esconder colunas técnicas aos leitores ---------- */
DENY SELECT ON gold.dim_cliente (hash_scd1, hash_scd2) TO rl_marketing_leitura;
GO

/* ---------- RLS no Warehouse (opcional, para quem consulta por SQL) ----------
   Reaproveita gold.rls_acesso_regiao. Ativar só depois de preencher essa tabela:
   quem não constar deixa de ver clientes. Nota: com RLS no Warehouse, o Direct Lake recorre
   a DirectQuery; para relatórios, preferir a RLS do modelo semântico (NB_40). */
CREATE OR ALTER FUNCTION seguranca.fn_filtro_regiao (@regiao AS VARCHAR(20))
RETURNS TABLE
WITH SCHEMABINDING
AS
RETURN
    SELECT 1 AS permitido
    FROM gold.rls_acesso_regiao AS a
    WHERE a.utilizador = USER_NAME()
      AND (a.regiao = 'Todas' OR a.regiao = @regiao);
GO
-- CREATE SECURITY POLICY seguranca.pol_regiao_cliente
--     ADD FILTER PREDICATE seguranca.fn_filtro_regiao(regiao) ON gold.dim_cliente
--     WITH (STATE = ON);
