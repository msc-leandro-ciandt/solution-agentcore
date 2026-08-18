# Plano: Histórico de Conversas (Padrão 2 — Memory + DynamoDB)

Baseado em `docs/SESSION_MANAGEMENT.md`, seguindo o "flavor" **Metadata only**: DynamoDB guarda nome/data/status de cada sessão para listagem rápida e ordenada; o conteúdo da conversa continua vindo do AgentCore Memory (que já funciona hoje).

## Memória de longo prazo

`use_long_term_memory: true` já foi setado no `config.yaml`. Falta apenas `cdk deploy` para aplicar — incluído no passo final deste plano.

## Arquitetura

```
Frontend                          API Gateway (reaproveita "FeedbackApi")      DynamoDB          AgentCore Memory
   |                                        |                                      |                    |
   |--- GET /sessions --------------------->|--- Query userId ------------------->|                    |
   |<-- [{id, name, updatedAt}, ...] -------|                                      |                    |
   |                                        |                                      |                    |
   |--- GET /sessions/{id} ----------------->|--- GetItem (nome/metadados) ------->|                    |
   |                                        |--- ListEvents(memoryId, actorId, sessionId) -------------->|
   |<-- {metadata, messages} ---------------|                                      |                    |
   |                                        |                                      |                    |
   |--- PUT /sessions/{id} (touch) -------->|--- PutItem (nome, updatedAt) ------->|                    |
   |                                        |                                      |                    |
   |--- DELETE /sessions/{id} ------------->|--- DeleteItem ---------------------->|                    |
```

O agente (`basic_agent.py`) continua escrevendo na Memory exatamente como já faz — nenhuma mudança no runtime do agente. O DynamoDB é uma tabela paralela, populada pela própria API.

## Decisão de design que precisa da sua aprovação: endpoint de "touch"

O doc diz "There is no `POST /sessions`" — mas isso descreve que **não é preciso criar uma sessão antes de conversar** (ela nasce implicitamente com um UUID gerado no cliente). Isso não resolve, porém, quem grava o *nome* e a *data de atualização* no DynamoDB (a tabela nova não escreve nada por conta própria).

Solução proposta: um endpoint `PUT /sessions/{id}` (upsert idempotente) que o **frontend chama automaticamente** depois da primeira mensagem de cada conversa, enviando um nome derivado da mensagem (truncada em 50 caracteres — estratégia mais simples do doc, sem custo/latência extra de chamar o modelo para gerar título). Isso mantém a tabela sempre atualizada sem tocar no container do agente.

**Pergunta**: tudo bem com essa abordagem, ou prefere nomes gerados pelo modelo (mais "bonito", porém com uma chamada extra ao LLM e mais latência)?

## Backend

### 1. DynamoDB — `{stack_name_base}-Sessions`
- PK `userId` (Cognito sub), SK `sessionId`
- Atributos: `name`, `status` ("active"), `createdAt`, `updatedAt`
- `PAY_PER_REQUEST`, `pointInTimeRecovery: true`, `RemovalPolicy.DESTROY` (dev)

### 2. Lambda `infra-cdk/lambdas/sessions/index.py`
Segue exatamente o padrão de `infra-cdk/lambdas/feedback/index.py` (Powertools `APIGatewayRestResolver`, CORS, claims do Cognito via `authorizer.claims["sub"]`).

- `GET /sessions` → `Query` na tabela por `userId`, ordenado por `updatedAt` desc
- `GET /sessions/{sessionId}` → lê metadata (DynamoDB `GetItem`) + `list_events(memoryId, actorId=userId, sessionId)` do AgentCore Memory (data plane), converte os eventos em `Message[]` no mesmo formato usado pelo frontend
- `PUT /sessions/{sessionId}` → upsert (`name`, `updatedAt`, `createdAt` se novo) — usado pelo "touch"
- `DELETE /sessions/{sessionId}` → `DeleteItem` no DynamoDB (autoritativo para a listagem). Também tenta, best-effort, apagar os eventos correspondentes na Memory via `list_events` + `delete_event` (se falhar parcialmente, não bloqueia a resposta — a sessão já desaparece da listagem, que é o que importa para o usuário)

IAM necessário: `dynamodb:Query/GetItem/PutItem/DeleteItem` na tabela nova + `bedrock-agentcore:ListEvents`, `bedrock-agentcore:DeleteEvent` no Memory (mesmo padrão do `MEMORY_INTEGRATION.md`).

### 3. CDK (`backend-construct.ts`)
Reaproveita a `RestApi` já existente ("FeedbackApi", variável `api`) e o `CognitoUserPoolsAuthorizer` já criado — não cria uma API Gateway nova. Adiciona:
```
const sessionsResource = api.root.addResource("sessions")
const sessionByIdResource = sessionsResource.addResource("{sessionId}")
sessionsResource.addMethod("GET", ..., { authorizer, authorizationType: COGNITO })
sessionByIdResource.addMethod("GET", ...)
sessionByIdResource.addMethod("PUT", ...)
sessionByIdResource.addMethod("DELETE", ...)
```
Passa `MEMORY_ID` (já disponível no construct) como env var da nova Lambda.

## Frontend

### 1. `frontend/src/services/sessionsService.ts` (novo)
Mesmo padrão de `feedbackService.ts`: lê a URL da API de `aws-exports.json` (novo campo `sessionsApiUrl`, resolvido a partir da mesma `FeedbackApiUrl` — é a mesma API, só path diferente, então na prática reutilizamos `feedbackApiUrl` trocando o sufixo). Funções: `listSessions`, `getSession`, `touchSession`, `deleteSession` — todas recebem `idToken`.

### 2. Persistência do `session_id` atual (reload não perde a conversa)
Em `ChatInterface.tsx`: `sessionId` passa a inicializar lendo `localStorage.getItem("fast_current_session_id")` (fallback para `crypto.randomUUID()`), e todo `setSessionId` grava de volta no localStorage. No mount, se havia um id persistido, chama `GET /sessions/{id}` para reconstruir os balões de mensagem (a conversa em si já está na Memory; isso só busca e exibe de novo).

### 3. Conectar o `ChatSidebar` (já existe, não usado)
- `ChatPage.tsx` passa a envolver o layout com `SidebarProvider` + renderizar `<ChatSidebar/>` ao lado do `<ChatInterface/>`
- Estado da lista de sessões sobe para `ChatPage` (via um hook simples `useChatSessions`), que busca `GET /sessions` no mount e depois de criar/apagar sessões
- `onSessionSelect`: chama `GET /sessions/{id}`, popula as mensagens e troca o `sessionId` ativo (equivalente a "retomar")
- `onNewChat`: gera novo UUID, limpa mensagens (reaproveita `startNewChat` já existente)
- Botão de excluir (novo, pequeno ícone de lixeira por item) chama `DELETE /sessions/{id}`

### 4. "Touch" automático
Depois que a primeira resposta do assistente é recebida com sucesso em uma sessão nova, `ChatInterface` chama `touchSession(sessionId, primeiraMensagem.slice(0,50), idToken)` uma vez. Chamadas subsequentes na mesma sessão só atualizam `updatedAt` (reenviando o mesmo nome já salvo, sem overhead perceptível).

## Arquivos afetados

| Arquivo | Ação |
|---|---|
| `infra-cdk/config.yaml` | ✅ já editado (`use_long_term_memory: true`) |
| `infra-cdk/lambdas/sessions/index.py` | novo |
| `infra-cdk/lib/backend-construct.ts` | editar (tabela DynamoDB, Lambda, rotas `/sessions`) |
| `frontend/src/services/sessionsService.ts` | novo |
| `frontend/src/components/chat/ChatSidebar.tsx` | pequeno ajuste (botão excluir) |
| `frontend/src/components/chat/ChatInterface.tsx` | editar (persistência localStorage, hidratação, touch) |
| `frontend/src/routes/ChatPage.tsx` | editar (SidebarProvider + ChatSidebar) |
| `scripts/deploy-frontend.py` | editar (novo campo `sessionsApiUrl` no aws-exports.json, se necessário) |

## Ordem de execução

1. `cdk deploy` já aplicando `use_long_term_memory: true` (rápido, isolado)
2. DynamoDB + Lambda `sessions` + rotas no CDK → build → deploy
3. Frontend: service, persistência, hidratação, sidebar conectado
4. Deploy do frontend (`scripts/deploy-frontend.py`)
5. Teste manual: criar 2 conversas, recarregar página, trocar entre elas pela sidebar, excluir uma

## Perguntas antes de eu começar

1. Nome da sessão por truncamento da primeira mensagem (simples) está ok, ou prefere título gerado por LLM (mais bonito, mais custo/latência)?
2. Ao excluir uma sessão, ok que os eventos na Memory sejam apagados em "melhor esforço" (pode não conseguir remover 100% se houver muitos eventos, mas a sessão já some da lista)?
3. Confirma que quer reaproveitar a API Gateway existente (`FeedbackApi`) para as rotas `/sessions`, em vez de criar uma API nova?

## Decisões confirmadas pelo usuário

1. **Título gerado por LLM** (não truncamento). Para não adicionar latência à conversa principal, a geração de título acontece dentro da chamada de "touch" (`PUT /sessions/{sessionId}`), que já é disparada pelo frontend em segundo plano, depois que a resposta do assistente já apareceu na tela — ou seja, não bloqueia o streaming do chat, só atualiza o nome na sidebar um instante depois.
   - Modelo: `us.anthropic.claude-3-haiku-20240307-v1:0` (rápido e barato, adequado para gerar só um título curto — ver `infra-cdk/BEDROCK_MODELS.md`).
   - A Lambda de sessions só chama o Bedrock **na primeira vez** que uma sessão é "touched" (quando ainda não existe `name` salvo). Chamadas seguintes na mesma sessão só atualizam `updatedAt`, sem nova chamada ao modelo (evita custo/latência repetidos).
   - Fallback: se a chamada ao Bedrock falhar ou não responder a tempo, usa truncamento da primeira mensagem como nome (nunca falha silenciosamente, nunca deixa a sessão sem nome).
   - Prompt: recebe a primeira mensagem do usuário + a primeira resposta do assistente, pede um título curto (até 6 palavras, em português).
   - IAM: a Lambda de sessions precisa de `bedrock:InvokeModel` restrito ao ARN do inference profile do Haiku.
2. **Exclusão em melhor esforço** confirmada — remove da listagem imediatamente (autoritativo via DynamoDB), tenta limpar eventos na Memory sem bloquear a resposta em caso de falha parcial.
3. **Reaproveitar a API Gateway existente** (FeedbackApi) confirmado — mais simples, mesma latência (é a mesma API, só uma rota nova), sem custo adicional de uma segunda API Gateway.

Plano aprovado. Implementação em andamento.

## Status final: ✅ Implementado, deployado e testado (18/08/2026)

### Long-term memory
`USE_LONG_TERM_MEMORY=true` confirmado no Runtime deployado. A extração de fatos (`FactExtractor`, namespace `/facts/{actorId}`) já estava rodando em segundo plano mesmo antes; agora o agente também **recupera** esses fatos em cada turno.

### Histórico de conversas
Todos os endpoints testados diretamente via `aws lambda invoke` contra a Lambda real:
- `GET /sessions` — lista vazia inicialmente, depois ordenada por `updatedAt` desc
- `PUT /sessions/{id}` (touch) — gera título via Bedrock no primeiro touch; toques seguintes só atualizam `updatedAt`
- `GET /sessions/{id}` — retorna metadata + histórico completo lido da AgentCore Memory, com texto legível
- `DELETE /sessions/{id}` — remove a metadata e some da listagem

### Bugs encontrados e corrigidos durante o teste manual

1. **Modelo Haiku legado bloqueado**: `claude-3-haiku-20240307-v1:0` está marcado pela AWS como "Legacy" e bloqueado por falta de uso recente (`ResourceNotFoundException: Access denied`). Trocado para `us.anthropic.claude-haiku-4-5-20251001-v1:0` (ativo). A Lambda tinha um fallback correto (título truncado), então o sistema nunca quebrou, apenas não gerava títulos bonitos até a correção.
2. **Parsing de conteúdo da Memory**: o `AgentCoreMemorySessionManager` do Strands grava cada turno como uma string JSON aninhada (não texto puro). Adicionada `_extract_message_text()` para desserializar corretamente antes de devolver ao frontend.
3. **Regressão de build do CDK**: partes de edições anteriores (`createSessionsTable`, `createSessionsApi`, ampliação de CORS) não persistiram em `backend-construct.ts` após uma possível compactação de contexto — detectado via `npm run build` (erro TS2551) e reaplicado.
4. **Erros de tipo no frontend**: `idToken` podia ser `null` (retorno do hook `useAuth`) onde as funções esperavam `string | undefined`; corrigido normalizando para `undefined` e capturando em uma const local para o TypeScript propagar o narrowing dentro de closures assíncronas.
5. **Regressão em testes**: adicionar `SidebarProvider`/`ChatSidebar` ao `ChatPage` introduziu uso de `window.matchMedia` (não implementado em jsdom) e tornou a renderização do `ChatInterface` assíncrona (hidratação de sessão). Corrigido com mock global de `matchMedia` em `src/test/setup.ts` e `waitFor`/`fc.asyncProperty` nos testes de `property-auth-routing.test.tsx`. Suite voltou ao baseline exato: 94 passando / 8 falhas (pré-existentes, estilo de aspas).

### Deploy final
- CDK: `cdk deploy --all` com sucesso (29 recursos novos/atualizados)
- Frontend: `python3 scripts/deploy-frontend.py` com sucesso, página respondendo HTTP 200
- Nenhuma mudança necessária em `scripts/deploy-frontend.py` (sessionsService.ts reaproveita `feedbackApiUrl` já existente)
