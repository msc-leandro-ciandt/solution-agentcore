# Plano: Consulta de Processos Judiciais + Digest Diário por Email

## Objetivo

1. Agente responde perguntas sobre 2 processos específicos (via chat no frontend), consultando a API Pública do DataJud (CNJ).
2. Email diário automático para leanpsilva@gmail.com e renatahellensouzagarcia@gmail.com com o status/atualizações dos 2 processos.

## Processos monitorados (fixos, configurados no deploy)

| Label | Tribunal | Número CNJ |
|---|---|---|
| Processo 1 | TJSC | 5084844-64.2026.8.24.0930 |
| Processo 2 | TJRS | 5015749-78.2026.8.21.0008 |

## Fonte de dados: API Pública DataJud (CNJ)

- Endpoint: `https://api-publica.datajud.cnj.jus.br/api_publica_{tjsc|tjrs}/_search`
- Auth: header `Authorization: APIKey <chave pública fixa do CNJ>` (não é segredo nosso — chave pública divulgada pelo CNJ, mas guardamos em SSM para poder trocar sem redeploy caso o CNJ a rotacione)
- Busca por `numeroProcesso` (Elasticsearch query), retorna: classe, assuntos, órgão julgador, grau, data de ajuizamento e lista de `movimentos` (data + descrição)
- Limitação conhecida: **não** retorna nome de partes, CPF, nem teor de petições/decisões — só metadados de capa e movimentações. Suficiente para responder "qual o status" / "teve movimentação".
- Escopo de segurança: a tool só aceita os 2 números de processo configurados no deploy (allowlist), não uma busca livre por qualquer processo do Brasil — evita virar uma ferramenta de consulta processual genérica exposta sem controle.

## Arquitetura de dados: cache no DynamoDB, não consulta live no chat

Decisão importante (confirmada com o usuário): **a tool do chat nunca chama o DataJud diretamente.** Só a Lambda do digest diário (Parte 2) fala com a API externa, 1x/dia, e grava o resultado em uma tabela DynamoDB (`ProcessDigestState`). A tool do chat (Parte 1) só lê essa tabela.

Motivos:
- Chat responde em milissegundos (leitura DynamoDB) em vez de depender de uma chamada HTTPS externa a cada pergunta.
- A Lambda acionada pelo chat não precisa de acesso à internet nem da API key do DataJud — reduz superfície de risco e permissões IAM.
- Status de processo judicial não muda a cada minuto; um snapshot de até 24h é suficiente para esse caso de uso.
- Menor dependência de disponibilidade de terceiros no caminho crítico do chat.

Trade-off aceito: logo após o deploy, a tabela está vazia até a primeira execução do digest (por isso a tarefa de "invocar a digest Lambda manualmente uma vez" antes do uso). Se o processo for atualizado no tribunal, o chat só reflete isso após o próximo digest diário (até 24h de atraso) — aceitável para este caso de uso, sem urgência de tempo real.

## Parte 1 — Tool de chat (Gateway + Lambda), seguindo o padrão existente do projeto

Arquivos novos, no mesmo padrão de `gateway/tools/sample_tool/`:

- `gateway/tools/consulta_processual/consulta_processual_lambda.py`
  - Handler segue exatamente o padrão do `sample_tool_lambda.py` (extrai tool name de `context.client_context.custom['bedrockAgentCoreToolName']`)
  - Tool: `consultar_processo_judicial(numero_processo?: str)`
    - Se `numero_processo` omitido, retorna resumo dos 2 processos
    - Valida que o número está na allowlist (env var `PROCESSOS_MONITORADOS`, JSON)
    - Lê o snapshot cacheado no DynamoDB (`DIGEST_STATE_TABLE_NAME`) e formata capa + últimos 5 movimentos em texto legível
    - Se não houver snapshot ainda (digest nunca rodou), retorna mensagem explícita em vez de dado inventado
- `gateway/tools/consulta_processual/tool_spec.json`
  - Schema com `numero_processo` (string, opcional)

### CDK (`infra-cdk/lib/backend-construct.ts`)

- Novo `lambda.Function` "ConsultaProcessualLambda" (mesmo padrão do `SampleToolLambda`)
  - Env vars: `PROCESSOS_MONITORADOS` (JSON dos 2 processos), `DIGEST_STATE_TABLE_NAME` (nome da tabela DynamoDB)
  - IAM: apenas `dynamodb:GetItem` na tabela `ProcessDigestState` — sem acesso à internet, sem API key do DataJud
- Novo `gateway.addLambdaTarget("ConsultaProcessualTarget", ...)`, `gatewayTargetName: "consulta-processual-target"`

### Cedar Policy (`gateway/policies/policy.cedar`)

- Novo bloco `permit` para a action `consulta-processual-target___consultar_processo_judicial`
- **Assunção**: como são só 2 usuários da mesma família e ambos processos são de interesse comum, libero a tool para qualquer usuário autenticado (department finance/engineering/guest — igual à Versão 1 do sample tool). Se você preferir que cada um só veja o próprio processo, eu ajusto para usar `context.input.numero_processo` + `principal.getTag("user_id")` (precisaria mapear qual processo pertence a qual UUID de usuário). **Me confirme se quer isolar ou manter compartilhado.**

## Parte 2 — Digest diário por email

### Novo recurso: DynamoDB `ProcessDigestState`

- PK: `numero_processo` (string)
- Atributos:
  - `dados_json` (string) — JSON completo do último `_source` retornado pelo DataJud (classe, assuntos, órgão julgador, movimentos, etc), ou `{"fonte": null}` se o processo não foi encontrado na última sincronização
  - `ultima_sincronizacao` (string, ISO 8601) — timestamp da última consulta bem-sucedida ao DataJud
  - `ultimo_movimento_codigo` / `ultimo_movimento_data` — usados só pela Lambda do digest para detectar "o que é novo desde ontem" antes de montar o email
- Esta é a **única fonte de dados da tool de chat** (Parte 1) — ver seção "Arquitetura de dados" acima

### Nova Lambda: `infra-cdk/lambdas/process-digest/index.py`

- Roda 1x/dia via EventBridge Scheduler
- Para cada processo monitorado: consulta DataJud, compara com o último estado salvo no DynamoDB
- Monta e envia email via **Amazon SES** (`send_email`) para as duas contas
- Atualiza o DynamoDB com o novo estado

### EventBridge Scheduler

- `Schedule.rate(Duration.days(1))` (ou `cron` para um horário fixo — **preciso que você confirme o horário preferido, ex: 8h BRT**)

### Amazon SES — passo manual necessário

Sua conta AWS está em **modo sandbox do SES** (confirmei via `aws sesv2 get-account`: `ProductionAccessEnabled: false`, limite de 200 emails/24h). Em sandbox, **tanto o remetente quanto os destinatários precisam ser verificados**. Como só há 2 destinatários (você e a Renata) e nenhum volume de envio real, **não é necessário pedir produção** — basta verificar os 2 emails uma vez.

O CDK vai criar as `EmailIdentity` para:
- leanpsilva@gmail.com (remetente e destinatário)
- renatahellensouzagarcia@gmail.com (destinatário)

Após o deploy, **vocês dois vão receber um email da AWS pedindo para clicar em um link de confirmação** — isso é obrigatório e manual, não posso automatizar (é uma verificação de posse do email pela própria AWS).

### Config (`infra-cdk/config.yaml`) — nova seção

```yaml
monitoring:
  notification_emails:
    - leanpsilva@gmail.com
    - renatahellensouzagarcia@gmail.com
  digest_schedule_cron: "cron(0 11 * * ? *)"  # 11:00 UTC = 08:00 BRT — AJUSTAR SE QUISER OUTRO HORÁRIO
  processes:
    - label: "Processo TJSC"
      tribunal: tjsc
      numero_processo: "5084844-64.2026.8.24.0930"
    - label: "Processo TJRS"
      tribunal: tjrs
      numero_processo: "5015749-78.2026.8.21.0008"
```

`config-manager.ts` (`AppConfig`) ganha um bloco `monitoring` opcional, com validação (regex simples do número CNJ, tribunal em `["tjrs","tjsc"]`).

## Resumo de arquivos afetados

| Arquivo | Ação |
|---|---|
| `gateway/tools/consulta_processual/consulta_processual_lambda.py` | novo |
| `gateway/tools/consulta_processual/tool_spec.json` | novo |
| `gateway/policies/policy.cedar` | editar (novo permit) |
| `infra-cdk/lib/backend-construct.ts` | editar (novo Lambda + Gateway target) |
| `infra-cdk/lib/utils/config-manager.ts` | editar (novo bloco `monitoring`) |
| `infra-cdk/config.yaml` | editar (novo bloco `monitoring`) |
| `infra-cdk/lambdas/process-digest/index.py` | novo |
| `infra-cdk/lib/backend-construct.ts` (ou novo construct) | editar (DynamoDB + EventBridge Scheduler + SES identities) |
| `patterns/strands-single-agent/basic_agent.py` | editar (SYSTEM_PROMPT menciona a nova capacidade) |

## Ordem de execução

1. Tool de consulta (Gateway + Lambda + Cedar) — testável isoladamente via `scripts/test-gateway.py` e depois no chat
2. Digest diário (DynamoDB + Lambda + Scheduler + SES)
3. `cdk deploy`
4. Verificação manual dos 2 emails no SES (clicar no link)
5. Teste manual: invocar a digest Lambda uma vez via CLI (`aws lambda invoke`) para validar o email antes de esperar o schedule

## Decisões confirmadas pelo usuário

1. **Acesso no chat**: compartilhado — Leandro e Renata fazem parte dos dois processos, então ambos podem consultar os dois. Cedar policy libera a tool para qualquer usuário autenticado (igual à Versão 1 do sample tool).
2. **Horário do email diário**: 08:00 (horário de Brasília) = `cron(0 11 * * ? *)` em UTC.
3. **Email diário**: confirmado, sempre envia um resumo, destacando movimentos novos desde o último envio.
4. **Verificação SES**: confirmado — cada um clica no link de verificação recebido por email após o deploy (passo manual único, obrigatório pela AWS, sem custo).

Plano aprovado. Implementação em andamento.

## Status final: ✅ Implementado, deployado e testado (17/08/2026)

Todos os componentes foram implementados, o deploy foi bem-sucedido, e o fluxo completo foi validado:

- **Chat**: `consultar_processo_judicial` testada de ponta a ponta (autenticação M2M com propagação de identidade, Cedar policy liberando a tool, leitura do cache DynamoDB) — retornou os 2 processos formatados corretamente.
- **Digest diário**: testado manualmente via `aws lambda invoke` — consultou o DataJud, populou o DynamoDB, e enviou email via SES para os 2 destinatários sem erro.
- **SES**: ambos os emails (`leanpsilva@gmail.com` e `renatahellensouzagarcia@gmail.com`) verificados com sucesso (`VerificationStatus: SUCCESS`).
- **Correção aplicada durante o teste**: a permissão IAM inicial só concedia `grantSendEmail` na identidade do remetente. O SES também exige permissão na identidade do destinatário quando ele é uma EmailIdentity verificada na mesma conta — corrigido concedendo a permissão em todas as identidades configuradas.
- **Scheduler**: `AWS::Scheduler::Schedule` criado e ativo, disparando `cron(0 11 * * ? *)` (08:00 horário de Brasília) todos os dias.

### Recursos AWS criados

| Recurso | Nome/ARN |
|---|---|
| DynamoDB | `juris-consult-process-digest` |
| Lambda (chat tool) | `juris-consult-...-ConsultaProcessualLambda` |
| Lambda (digest) | `juris-consult-jurisconsultbackendProcessDigestLamb-1F8ssfruJ09E` |
| Gateway Target | `consulta-processual-target` |
| SSM Parameter | `/juris-consult/datajud_api_key` |
| EventBridge Schedule | `juris-consult-backend/ProcessDigestSchedule` |
| SES Identities | `leanpsilva@gmail.com`, `renatahellensouzagarcia@gmail.com` |

### Próxima execução automática

O digest já rodou uma vez manualmente (dados cacheados e email de teste enviado). A próxima execução automática ocorre no próximo horário agendado (08:00 BRT).
