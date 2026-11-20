/* =====================================================================================
   WH_01 — Modelo dimensional (esquema em estrela)            Warehouse: WH_Gold

   Boas práticas aplicadas:
   - Chaves substitutas (sk_*) com IDENTITY nas dimensões; os factos guardam sk_*.
   - dim_cliente em SCD tipo 2 (histórico de segmento, rendimento, distrito e consentimento).
   - Membro "Desconhecido" (id de negócio -1) em cada dimensão → factos nunca ficam órfãos.
   - PK/FK declaradas NOT ENFORCED (documentam o modelo e ajudam o otimizador).
   - Tipos estreitos (VARCHAR com tamanho, DECIMAL com escala) → melhor compressão e Direct Lake.

   ⚠ Recria as tabelas Gold (DROP). Para alterações em produção usar scripts de migração.
   ===================================================================================== */

/* ---------- dim_data ---------- */
DROP TABLE IF EXISTS gold.dim_data;
CREATE TABLE gold.dim_data (
    id_data         INT           NOT NULL,
    data            DATE          NOT NULL,
    ano             INT           NOT NULL,
    trimestre       VARCHAR(2)    NOT NULL,
    ano_trimestre   VARCHAR(8)    NOT NULL,
    num_mes         INT           NOT NULL,
    mes             VARCHAR(12)   NOT NULL,
    mes_abrev       VARCHAR(3)    NOT NULL,
    ano_mes         VARCHAR(7)    NOT NULL,
    semana_iso      INT           NOT NULL,
    dia_semana      VARCHAR(10)   NOT NULL,
    num_dia_semana  INT           NOT NULL,
    fim_de_semana   BIT           NOT NULL
);
ALTER TABLE gold.dim_data ADD CONSTRAINT pk_dim_data PRIMARY KEY NONCLUSTERED (id_data) NOT ENFORCED;

/* ---------- dim_produto (SCD1) ---------- */
DROP TABLE IF EXISTS gold.dim_produto;
CREATE TABLE gold.dim_produto (
    sk_produto        BIGINT IDENTITY,
    id_produto        INT            NOT NULL,
    nome_produto      VARCHAR(60)    NOT NULL,
    categoria         VARCHAR(40)    NOT NULL,
    margem_estimada   DECIMAL(9,4)   NOT NULL,
    hash_origem       VARCHAR(64)    NULL,
    data_criacao      DATETIME2(3)   NOT NULL,
    data_atualizacao  DATETIME2(3)   NOT NULL
);
ALTER TABLE gold.dim_produto ADD CONSTRAINT pk_dim_produto PRIMARY KEY NONCLUSTERED (sk_produto) NOT ENFORCED;

/* ---------- dim_campanha (SCD1, com atributos do produto desnormalizados) ---------- */
DROP TABLE IF EXISTS gold.dim_campanha;
CREATE TABLE gold.dim_campanha (
    sk_campanha       BIGINT IDENTITY,
    id_campanha       VARCHAR(20)    NOT NULL,
    nome_campanha     VARCHAR(120)   NOT NULL,
    canal             VARCHAR(20)    NOT NULL,
    tipo_canal        VARCHAR(20)    NOT NULL,
    objetivo          VARCHAR(20)    NOT NULL,
    segmento_alvo     VARCHAR(20)    NOT NULL,
    id_produto        INT            NOT NULL,
    produto_campanha  VARCHAR(60)    NOT NULL,
    categoria_produto VARCHAR(40)    NOT NULL,
    data_inicio       DATE           NULL,
    data_fim          DATE           NULL,
    duracao_dias      INT            NULL,
    orcamento         DECIMAL(18,2)  NOT NULL,
    hash_origem       VARCHAR(64)    NULL,
    data_criacao      DATETIME2(3)   NOT NULL,
    data_atualizacao  DATETIME2(3)   NOT NULL
);
ALTER TABLE gold.dim_campanha ADD CONSTRAINT pk_dim_campanha PRIMARY KEY NONCLUSTERED (sk_campanha) NOT ENFORCED;

/* ---------- dim_cliente (SCD2) ---------- */
DROP TABLE IF EXISTS gold.dim_cliente;
CREATE TABLE gold.dim_cliente (
    sk_cliente              BIGINT IDENTITY,
    id_cliente              INT            NOT NULL,
    -- tipo 2 (geram nova versão)
    segmento                VARCHAR(20)    NOT NULL,
    escalao_rendimento      VARCHAR(15)    NOT NULL,
    distrito                VARCHAR(40)    NOT NULL,
    regiao                  VARCHAR(20)    NOT NULL,
    consentimento_marketing BIT            NOT NULL,
    -- tipo 1 (sobrepostos na versão atual)
    data_nascimento         DATE           NULL,
    idade                   INT            NULL,
    faixa_etaria            VARCHAR(10)    NOT NULL,
    genero                  VARCHAR(5)     NOT NULL,
    canal_preferido         VARCHAR(20)    NOT NULL,
    data_adesao             DATE           NULL,
    antiguidade_anos        INT            NULL,
    escalao_antiguidade     VARCHAR(12)    NOT NULL,
    tem_email               BIT            NOT NULL,
    tem_app                 BIT            NOT NULL,
    -- controlo SCD2
    hash_scd2               VARCHAR(64)    NULL,
    hash_scd1               VARCHAR(64)    NULL,
    valido_de               DATE           NOT NULL,
    valido_ate              DATE           NOT NULL,
    registo_atual           BIT            NOT NULL,
    data_criacao            DATETIME2(3)   NOT NULL,
    data_atualizacao        DATETIME2(3)   NOT NULL
);
ALTER TABLE gold.dim_cliente ADD CONSTRAINT pk_dim_cliente PRIMARY KEY NONCLUSTERED (sk_cliente) NOT ENFORCED;

/* ---------- fact_contactos (grão: 1 contacto de campanha a 1 cliente) ---------- */
DROP TABLE IF EXISTS gold.fact_contactos;
CREATE TABLE gold.fact_contactos (
    id_contacto     VARCHAR(12)   NOT NULL,     -- dimensão degenerada
    sk_campanha     BIGINT        NOT NULL,
    sk_cliente      BIGINT        NOT NULL,     -- versão do cliente à data do envio
    id_data_envio   INT           NOT NULL,
    hora_envio      INT           NULL,
    enviado         INT           NOT NULL,
    entregue        INT           NOT NULL,
    aberto          INT           NOT NULL,
    clicado         INT           NOT NULL,
    convertido      INT           NOT NULL,
    id_lote         VARCHAR(100)  NULL,
    data_carga      DATETIME2(3)  NOT NULL
);
ALTER TABLE gold.fact_contactos ADD CONSTRAINT pk_fact_contactos PRIMARY KEY NONCLUSTERED (id_contacto) NOT ENFORCED;

/* ---------- fact_conversoes (grão: 1 contratação atribuída a uma campanha) ---------- */
DROP TABLE IF EXISTS gold.fact_conversoes;
CREATE TABLE gold.fact_conversoes (
    id_conversao        VARCHAR(20)    NOT NULL,
    id_contacto         VARCHAR(12)    NULL,
    sk_campanha         BIGINT         NOT NULL,
    sk_cliente          BIGINT         NOT NULL,
    sk_produto          BIGINT         NOT NULL,
    id_data_conversao   INT            NOT NULL,
    canal_conversao     VARCHAR(20)    NULL,
    tipo_atribuicao     VARCHAR(20)    NOT NULL,   -- 'Clique' | 'Janela 30 dias'
    dias_ate_conversao  INT            NULL,
    valor_contratado    DECIMAL(18,2)  NOT NULL,
    receita_estimada    DECIMAL(18,2)  NOT NULL,   -- valor × margem anual estimada
    id_lote             VARCHAR(100)   NULL,
    data_carga          DATETIME2(3)   NOT NULL
);
ALTER TABLE gold.fact_conversoes ADD CONSTRAINT pk_fact_conversoes PRIMARY KEY NONCLUSTERED (id_conversao) NOT ENFORCED;

/* ---------- fact_custos_campanha (grão: campanha × dia) ---------- */
DROP TABLE IF EXISTS gold.fact_custos_campanha;
CREATE TABLE gold.fact_custos_campanha (
    id_campanha   VARCHAR(20)    NOT NULL,
    sk_campanha   BIGINT         NOT NULL,
    id_data       INT            NOT NULL,
    custo         DECIMAL(18,2)  NOT NULL,
    impressoes    BIGINT         NULL,
    id_lote       VARCHAR(100)   NULL,
    data_carga    DATETIME2(3)   NOT NULL
);

/* ---------- cliente_envolvimento (snapshot analítico, versão atual do cliente) ---------- */
DROP TABLE IF EXISTS gold.cliente_envolvimento;
CREATE TABLE gold.cliente_envolvimento (
    sk_cliente               BIGINT         NOT NULL,
    id_cliente               INT            NOT NULL,
    n_contactos              INT            NOT NULL,
    n_aberturas              INT            NOT NULL,
    n_cliques                INT            NOT NULL,
    n_conversoes             INT            NOT NULL,
    valor_contratado         DECIMAL(18,2)  NOT NULL,
    dias_desde_ultimo_clique INT            NULL,
    score_envolvimento       INT            NOT NULL,   -- 0 a 100
    nivel_envolvimento       VARCHAR(12)    NOT NULL,   -- Alto | Médio | Baixo | Inativo
    data_calculo             DATETIME2(3)   NOT NULL
);

/* ---------- Acesso por região (usado pela RLS do modelo semântico) ---------- */
DROP TABLE IF EXISTS gold.rls_acesso_regiao;
CREATE TABLE gold.rls_acesso_regiao (
    utilizador  VARCHAR(256)  NOT NULL,   -- UPN (e-mail Entra ID)
    regiao      VARCHAR(20)   NOT NULL    -- 'Todas' = sem restrição
);
GO

/* ---------- Chaves estrangeiras (NOT ENFORCED) ---------- */
ALTER TABLE gold.fact_contactos       ADD CONSTRAINT fk_ct_campanha FOREIGN KEY (sk_campanha)       REFERENCES gold.dim_campanha (sk_campanha) NOT ENFORCED;
ALTER TABLE gold.fact_contactos       ADD CONSTRAINT fk_ct_cliente  FOREIGN KEY (sk_cliente)        REFERENCES gold.dim_cliente  (sk_cliente)  NOT ENFORCED;
ALTER TABLE gold.fact_contactos       ADD CONSTRAINT fk_ct_data     FOREIGN KEY (id_data_envio)     REFERENCES gold.dim_data     (id_data)     NOT ENFORCED;
ALTER TABLE gold.fact_conversoes      ADD CONSTRAINT fk_cv_campanha FOREIGN KEY (sk_campanha)       REFERENCES gold.dim_campanha (sk_campanha) NOT ENFORCED;
ALTER TABLE gold.fact_conversoes      ADD CONSTRAINT fk_cv_cliente  FOREIGN KEY (sk_cliente)        REFERENCES gold.dim_cliente  (sk_cliente)  NOT ENFORCED;
ALTER TABLE gold.fact_conversoes      ADD CONSTRAINT fk_cv_produto  FOREIGN KEY (sk_produto)        REFERENCES gold.dim_produto  (sk_produto)  NOT ENFORCED;
ALTER TABLE gold.fact_conversoes      ADD CONSTRAINT fk_cv_data     FOREIGN KEY (id_data_conversao) REFERENCES gold.dim_data     (id_data)     NOT ENFORCED;
ALTER TABLE gold.fact_custos_campanha ADD CONSTRAINT fk_cs_campanha FOREIGN KEY (sk_campanha)       REFERENCES gold.dim_campanha (sk_campanha) NOT ENFORCED;
ALTER TABLE gold.fact_custos_campanha ADD CONSTRAINT fk_cs_data     FOREIGN KEY (id_data)           REFERENCES gold.dim_data     (id_data)     NOT ENFORCED;
GO

/* ---------- Membros "Desconhecido" ---------- */
DECLARE @agora DATETIME2(3) = SYSUTCDATETIME();
INSERT INTO gold.dim_produto (id_produto, nome_produto, categoria, margem_estimada, hash_origem, data_criacao, data_atualizacao)
VALUES (-1, 'Desconhecido', 'Desconhecido', 0, NULL, @agora, @agora);

INSERT INTO gold.dim_campanha (id_campanha, nome_campanha, canal, tipo_canal, objetivo, segmento_alvo, id_produto,
                               produto_campanha, categoria_produto, data_inicio, data_fim, duracao_dias, orcamento,
                               hash_origem, data_criacao, data_atualizacao)
VALUES ('-1', 'Desconhecida', 'Desconhecido', 'Desconhecido', 'Desconhecido', 'Desconhecido', -1,
        'Desconhecido', 'Desconhecido', NULL, NULL, NULL, 0, NULL, @agora, @agora);

INSERT INTO gold.dim_cliente (id_cliente, segmento, escalao_rendimento, distrito, regiao, consentimento_marketing,
                              data_nascimento, idade, faixa_etaria, genero, canal_preferido, data_adesao,
                              antiguidade_anos, escalao_antiguidade, tem_email, tem_app, hash_scd2, hash_scd1,
                              valido_de, valido_ate, registo_atual, data_criacao, data_atualizacao)
VALUES (-1, 'Desconhecido', 'Desconhecido', 'Desconhecido', 'Desconhecida', 0, NULL, NULL, 'N/D', 'N/D',
        'Desconhecido', NULL, NULL, 'N/D', 0, 0, NULL, NULL, '1900-01-01', '9999-12-31', 1, @agora, @agora);

/* Reiniciar watermarks (as tabelas foram recriadas) */
UPDATE ctl.watermark SET valor = '1900-01-01', data_atualizacao = SYSUTCDATETIME();

/* Acessos de exemplo para a RLS — substituir por utilizadores reais do tenant */
INSERT INTO gold.rls_acesso_regiao VALUES
    ('marketing.lider@empresa.pt', 'Todas'),
    ('gestor.norte@empresa.pt',    'Norte'),
    ('gestor.lisboa@empresa.pt',   'Grande Lisboa');
GO
