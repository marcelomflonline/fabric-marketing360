# %% [markdown]
# # NB_Config — configuração central (metadata-driven)
# Incluído pelos outros notebooks com `%run NB_Config`. **Não tem lógica, só metadados.**
#
# Para acrescentar uma nova fonte basta criar uma entrada em `ENTIDADES`, escrever a função
# `transformar_<entidade>` em `NB_Transformacoes` e (se for para a Gold) o procedimento no Warehouse.
# Nenhum outro notebook precisa de ser alterado.

# %%
PROJETO = "marketing360"

# Itens Fabric (resolvidos por nome no workspace atual — iguais em DEV e PRD)
LH_BRONZE = "LH_Bronze"
LH_SILVER = "LH_Silver"
WH_GOLD = "WH_Gold"

# Lakehouses criados com "Lakehouse schemas" (predefinição atual do Fabric). Se não, pôr False.
USA_ESQUEMAS = True
ESQUEMA = "dbo"

# Pastas em LH_Bronze/Files
PASTA_LANDING = "landing"     # onde chegam os ficheiros
PASTA_ARQUIVO = "arquivo"     # para onde vão depois de ingeridos com sucesso
PASTA_REJEITADOS = "rejeitados"  # ficheiros que falharam a leitura

# Retenção (dias) usada pela manutenção Delta
RETENCAO_VACUUM_HORAS = 168

# Tabelas operacionais (vivem no LH_Silver para serem consultáveis pelo SQL endpoint)
OPS_FICHEIROS = "ops_ficheiros_processados"
OPS_WATERMARK = "ops_watermark"
OPS_QUARENTENA = "ops_quarentena"
OPS_QUALIDADE = "ops_resultado_qualidade"
OPS_LOG = "ops_log_execucao"

# %% [markdown]
# ## Entidades
# - `padrao_ficheiro`: glob dos ficheiros em `landing/<entidade>/`
# - `chaves`: chave de negócio (deduplicação e MERGE)
# - `regras`: regras de qualidade aplicadas DEPOIS da tipagem.
#   `acao = "rejeitar"` → linha vai para quarentena; `acao = "alertar"` → passa, mas é contada.

# %%
ENTIDADES = {
    "produtos": {
        "padrao_ficheiro": "produtos_*.csv",
        "chaves": ["id_produto"],
        "regras": [
            {"nome": "id_produto_preenchido", "expressao": "id_produto IS NOT NULL", "acao": "rejeitar"},
            {"nome": "margem_entre_0_e_1", "expressao": "margem_estimada BETWEEN 0 AND 1", "acao": "rejeitar"},
        ],
    },
    "campanhas": {
        "padrao_ficheiro": "campanhas_*.csv",
        "chaves": ["id_campanha"],
        "regras": [
            {"nome": "id_campanha_preenchido", "expressao": "id_campanha IS NOT NULL", "acao": "rejeitar"},
            {"nome": "datas_validas", "expressao": "data_inicio IS NOT NULL AND data_fim >= data_inicio", "acao": "rejeitar"},
            {"nome": "canal_conhecido", "expressao": "canal IN ('Email','SMS','Push App','Redes Sociais','Display','Balcão')", "acao": "rejeitar"},
            {"nome": "orcamento_positivo", "expressao": "orcamento > 0", "acao": "alertar"},
        ],
    },
    "clientes": {
        "padrao_ficheiro": "clientes_*.csv",
        "chaves": ["id_cliente"],
        "regras": [
            {"nome": "id_cliente_preenchido", "expressao": "id_cliente IS NOT NULL", "acao": "rejeitar"},
            {"nome": "maior_de_idade", "expressao": "idade >= 18", "acao": "rejeitar"},
            {"nome": "distrito_conhecido", "expressao": "distrito <> 'Desconhecido'", "acao": "alertar"},
            {"nome": "segmento_conhecido", "expressao": "segmento <> 'Desconhecido'", "acao": "alertar"},
        ],
    },
    "contactos": {
        "padrao_ficheiro": "contactos_*.csv",
        "chaves": ["id_contacto"],
        "regras": [
            {"nome": "id_contacto_preenchido", "expressao": "id_contacto IS NOT NULL", "acao": "rejeitar"},
            {"nome": "data_envio_valida", "expressao": "data_hora_envio IS NOT NULL", "acao": "rejeitar"},
            {"nome": "campanha_existe", "expressao": "_campanha_existe", "acao": "rejeitar"},
            {"nome": "cliente_existe", "expressao": "_cliente_existe", "acao": "rejeitar"},
            {"nome": "funil_coerente", "expressao": "flag_clicado <= flag_aberto AND flag_aberto <= flag_entregue", "acao": "rejeitar"},
            {"nome": "cliente_com_consentimento", "expressao": "_cliente_consentiu", "acao": "alertar"},
        ],
    },
    "conversoes": {
        "padrao_ficheiro": "conversoes_*.csv",
        "chaves": ["id_conversao"],
        "regras": [
            {"nome": "id_conversao_preenchido", "expressao": "id_conversao IS NOT NULL", "acao": "rejeitar"},
            {"nome": "valor_nao_negativo", "expressao": "valor_contratado >= 0", "acao": "rejeitar"},
            {"nome": "campanha_existe", "expressao": "_campanha_existe", "acao": "rejeitar"},
            {"nome": "data_conversao_valida", "expressao": "data_conversao IS NOT NULL", "acao": "rejeitar"},
        ],
    },
    "custos_campanha": {
        "padrao_ficheiro": "custos_campanha_*.csv",
        "chaves": ["id_campanha", "data"],
        "regras": [
            {"nome": "custo_nao_negativo", "expressao": "custo >= 0", "acao": "rejeitar"},
            {"nome": "campanha_existe", "expressao": "_campanha_existe", "acao": "rejeitar"},
        ],
    },
}

# Ordem de dependências da camada Silver (usada pelo orquestrador)
DEPENDENCIAS_SILVER = {
    "produtos": [],
    "campanhas": [],
    "clientes": [],
    "contactos": ["campanhas", "clientes"],
    "conversoes": ["campanhas", "contactos"],
    "custos_campanha": ["campanhas"],
}
