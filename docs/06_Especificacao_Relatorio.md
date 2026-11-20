# 06 — Especificação do relatório `RPT_Marketing360`

**Público:** direção e equipa de Marketing. **Tema:** `src/powerbi/Tema_Marketing360.json`.
**Tela:** 16:9 (1280 × 720). **Regra de ouro:** cada página responde a uma pergunta. No máximo 6 a 8 visuais por página.

## Cabeçalho comum (todas as páginas)
Título da página (medida `Título Página` na pág. 2) · `Última Atualização` · segmentações sincronizadas:
`Data[ano_trimestre]`, `Campanha[canal]`, `Campanha[categoria_produto]`, `Cliente[segmento]`.

## Página 1 — Visão Geral ("Estamos a ganhar dinheiro com o marketing?")
| Visual | Campos |
|---|---|
| 6 cartões (KPI) | Custo · Conversões · Valor Contratado · Receita Estimada · ROI · CPA |
| Linhas e colunas | Eixo `Data[ano_mes]` · colunas: Custo · linha: Conversões |
| Barras horizontais | `Campanha[canal]` × ROI · cor por **valor de campo** = `Cor ROI` |
| Funil | Contactos Enviados → Entregues → Aberturas → Cliques → Conversões |
| Cartão de alerta | `Contactos sem Consentimento` (vermelho se > 0) |

## Página 2 — Campanhas ("Quais continuar, quais parar?")
| Visual | Campos |
|---|---|
| Tabela | nome_campanha, canal, Orçamento, Custo, Execução do Orçamento, Conversões, CPA, ROI (barras de dados), Ranking ROI Campanha |
| Dispersão | X = Custo · Y = Receita Estimada · tamanho = Conversões · legenda = canal · linha de referência y = x (ROI 0) |
| Detalhe (drill-through) | Página oculta "Detalhe Campanha": funil e evolução diária da campanha selecionada |

## Página 3 — Clientes e Segmentos ("Quem responde?")
| Visual | Campos |
|---|---|
| Matriz | linhas `Cliente[segmento]` · colunas `Cliente[faixa_etaria]` · Taxa de Conversão (mapa de calor) |
| Barras | `Cliente[regiao]` × Conversões e Taxa de Conversão |
| Anel | `Envolvimento[nivel_envolvimento]` × contagem |
| Cartões | Clientes na Base · % Consentimento · Oportunidades (Alto sem Conversão) |
| Tabela "Próximos a contactar" | id_cliente, segmento, regiao, score_envolvimento, n_cliques — filtro nível = Alto e n_conversoes = 0 (exportável para a próxima campanha) |

## Página 4 — Otimização de Envio ("Quando e como comunicar?")
| Visual | Campos |
|---|---|
| Matriz (mapa de calor) | linhas `Contactos[hora_envio]` · colunas `Data[dia_semana]` · CTR |
| Colunas agrupadas | `Campanha[canal]` × Taxa de Abertura, CTR, Click-to-Open |
| Barras | `Produto[categoria]` × Dias até Conversão |

## Boas práticas de desenho
- Números à esquerda e em cima (leitura em Z); os KPI primeiro, o detalhe depois.
- Cores com significado consistente (verde = bom, vermelho = mau). Nunca a cor como único sinal: usar também ícones e rótulos.
- Texto alternativo em todos os visuais e ordem de tabulação definida (acessibilidade).
- Sem segmentações duplicadas: usar o painel de filtros para filtros secundários.
- Medidas sempre a partir do modelo (nada de agregações implícitas): `Discourage implicit measures` ativo no modelo.
- Página "Sobre" com definições dos KPI (copiar de `docs/04`) e a data de atualização.

## Conclusões esperadas com os dados de exemplo
Email e Push App têm o melhor ROI (custo por contacto quase nulo). Redes Sociais e Display ficam com ROI
negativo neste modelo de atribuição *last-touch*. O Balcão converte cerca de 10× mais, mas com o CPA mais alto.
O segmento Jovem responde melhor ao digital.
