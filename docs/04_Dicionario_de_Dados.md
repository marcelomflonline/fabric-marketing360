# 04 — Dicionário de dados (Gold)

## Dimensões
**gold.dim_cliente** — SCD tipo 2, uma linha por versão do cliente
| Coluna | Tipo | Descrição |
|---|---|---|
| sk_cliente | BIGINT | Chave substituta (IDENTITY) |
| id_cliente | INT | Chave de negócio (-1 = Desconhecido) |
| segmento | VARCHAR | Massa, Afluente, Premium, Jovem, ENI · **tipo 2** |
| escalao_rendimento | VARCHAR | Rendimento mensal declarado · **tipo 2** |
| distrito / regiao | VARCHAR | Morada principal · **tipo 2** |
| consentimento_marketing | BIT | Autoriza comunicações de marketing (RGPD) · **tipo 2** |
| data_nascimento | DATE | **Mascarada** para leitores |
| idade / faixa_etaria | INT / VARCHAR | Calculadas à data de extração |
| genero, canal_preferido, tem_email, tem_app | — | Tipo 1 (sobrepostos) |
| data_adesao / antiguidade_anos / escalao_antiguidade | — | Relação com o banco |
| valido_de / valido_ate / registo_atual | DATE / DATE / BIT | Validade da versão (`9999-12-31` = atual) |

**gold.dim_campanha** — SCD1: id_campanha, nome, canal (Email, SMS, Push App, Redes Sociais, Display, Balcão),
tipo_canal (Digital próprio, Media paga, Presencial), objetivo (Aquisição, Cross-sell, Retenção), segmento_alvo,
produto_campanha, categoria_produto, datas, duração e orçamento.

**gold.dim_produto** — SCD1: id_produto, nome_produto, categoria, margem_estimada (margem anual estimada sobre o valor).

**gold.dim_data** — calendário 2024–2027 em português (mês, dia da semana, trimestre, semana ISO, fim de semana).

## Factos
| Tabela | Grão | Medidas base |
|---|---|---|
| fact_contactos | 1 contacto de 1 campanha a 1 cliente | enviado, entregue, aberto, clicado, convertido (0/1) |
| fact_conversoes | 1 contratação atribuída a 1 campanha | valor_contratado, receita_estimada, dias_ate_conversao; tipo_atribuicao |
| fact_custos_campanha | campanha × dia | custo, impressoes |
| cliente_envolvimento | 1 cliente (versão atual), snapshot | n_contactos, n_aberturas, n_cliques, n_conversoes, score_envolvimento (0–100), nivel_envolvimento |

## KPIs (medidas do modelo)
| KPI | Definição |
|---|---|
| Taxa de Entrega | Entregues ÷ Enviados |
| Taxa de Abertura | Aberturas ÷ Entregues |
| CTR | Cliques ÷ Entregues |
| Click-to-Open | Cliques ÷ Aberturas |
| Taxa de Conversão | Conversões ÷ Enviados |
| Receita Estimada | Σ valor_contratado × margem_estimada do produto |
| CPA / CPC / CPM | Custo ÷ Conversões / ÷ Cliques / ÷ Impressões × 1000 |
| ROI | (Receita Estimada − Custo) ÷ Custo |
| ROAS | Receita Estimada ÷ Custo |
| Execução do Orçamento | Custo ÷ Orçamento |
| Score de envolvimento | 30 × taxa de abertura + (25 se 1 clique, 40 se 2+) + 30 se converteu |
| Contactos sem Consentimento | Contactos a clientes cuja versão **à data do envio** não tinha consentimento (meta = 0) |

## Linhagem
`landing/<ent>/<ent>_AAAAMMDD.csv` → `LH_Bronze.<ent>` (`_ficheiro_origem`, `_linha`, `_id_lote`) →
`LH_Silver.<ent>` (`_data_extracao`, `_hash_linha`, `_data_processamento`) → `WH_Gold.gold.*` (`id_lote`, `data_carga`).
Cada linha da Gold pode ser rastreada até ao ficheiro e à linha de origem.
