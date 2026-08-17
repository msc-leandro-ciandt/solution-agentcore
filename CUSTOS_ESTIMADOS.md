# Custos Mensais Estimados - JurisConsult

Estimativa para uso familiar (2 usuários: Leandro e Renata), consultando o chat esporadicamente e recebendo 1 email/dia sobre 2 processos.

## Custos já existentes (infraestrutura atual)

| Serviço | Uso estimado | Custo/mês |
|---|---|---|
| Cognito User Pool (ESSENTIALS tier) | 2 usuários ativos | ~$0.50 |
| Amplify Hosting | build + hosting leve | ~$1.00 |
| Lambda (feedback, oauth2, cedar, etc) | poucas invocações | ~$0.20 |
| DynamoDB (feedback) | on-demand, uso baixo | ~$0.10 |
| S3 (staging + código do agente) | poucos MB | ~$0.10 |
| API Gateway (feedback) | poucas chamadas | ~$0.20 |
| CloudWatch Logs | retenção 7 dias | ~$0.20 |
| AgentCore Gateway + Runtime (infra, sem contar tokens) | idle a maior parte do tempo | ~$0.50 |
| **Subtotal infraestrutura** | | **~$2.80/mês** |

## Custo do modelo (Bedrock — Claude Sonnet 4.5)

Este é o item mais variável, pois depende de quantas perguntas vocês fazem no chat.

- Input: $3.00 / milhão de tokens
- Output: $15.00 / milhão de tokens

Cenário realista para uso familiar (chat esporádico sobre 2 processos):

| Cenário | Perguntas/mês | Tokens médios/pergunta (in+out) | Custo/mês |
|---|---|---|---|
| Uso leve | ~30 (1/dia) | ~2.000 | ~$0.30 |
| Uso moderado | ~150 (5/dia) | ~2.000 | ~$1.50 |
| Uso intenso | ~600 (20/dia) | ~2.000 | ~$6.00 |

Para o caso de vocês dois (dúvidas pontuais sobre 2 processos), o cenário **leve a moderado** é o mais provável: **$0.30 a $1.50/mês**.

## Custo dos novos componentes (consulta + digest diário)

| Componente | Detalhe | Custo/mês |
|---|---|---|
| API Pública DataJud (CNJ) | Gratuita, sem custo AWS | $0.00 |
| Lambda "consulta-processual" (chat) | poucas invocações | ~$0.00 (free tier) |
| Lambda "process-digest" (email diário) | 30 execuções/mês, ~5s cada | ~$0.00 (free tier) |
| EventBridge Scheduler | 1 disparo/dia = 30/mês | ~$0.00 (free tier cobre 14M/mês) |
| DynamoDB (estado dos processos) | tabela pequena, on-demand | ~$0.05 |
| Amazon SES (email) | 2 destinatários × 30 dias = 60 emails/mês | ~$0.01 (primeiros 62k emails/mês grátis se enviado de dentro da AWS; mesmo fora, é $0.10/1000 emails) |
| **Subtotal novos componentes** | | **~$0.10/mês** |

## Total estimado

| Categoria | Custo/mês |
|---|---|
| Infraestrutura base | ~$2.80 |
| Bedrock (modelo, uso leve-moderado) | ~$0.30 – $1.50 |
| Novos componentes (consulta + digest) | ~$0.10 |
| **TOTAL** | **~$3.20 – $4.40/mês** |

## Coisas que NÃO estão incluídas nesse valor

- **Long-term memory** (`use_long_term_memory: true`) — está desativado. Se ativar: +$0.75/1.000 registros salvos + $0.50/1.000 recuperações.
- **NAT Gateway** — só existe se vocês migrarem para `network_mode: VPC`. Custa ~$32/mês fixo + tráfego, bem mais caro que tudo isso junto. Não recomendo para este caso de uso.
- **Custos fora do free tier da AWS** caso a conta perca elegibilidade do free tier (12 meses da criação da conta).

## Como isso foi calculado

- Preços de Bedrock confirmados via busca em [aws.amazon.com/bedrock/pricing](https://aws.amazon.com/bedrock/pricing/) (Claude Sonnet 4.5: $3/M input, $15/M output tokens).
- Preços de Lambda, DynamoDB, EventBridge, SES: níveis gratuitos padrão da AWS (Lambda: 1M requests + 400.000 GB-s grátis/mês; SES: $0.10 por 1.000 emails além da faixa gratuita; EventBridge Scheduler: 14M invocações grátis/mês).
- Não é uma cobrança automática — é só uma estimativa. O valor real aparece no **Cost Explorer** da sua conta AWS depois de rodar por um mês.

## Como acompanhar o custo real

```bash
aws ce get-cost-and-usage \
  --time-period Start=2026-08-01,End=2026-08-31 \
  --granularity MONTHLY \
  --metrics "UnblendedCost" \
  --group-by Type=DIMENSION,Key=SERVICE
```

Ou pelo Console: **AWS Cost Explorer** → filtrar por tag `Project: JurisConsult`.
