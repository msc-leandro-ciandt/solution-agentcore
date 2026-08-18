# Quick Debug Steps - Session Switching Bug

Adicionei logging detalhado no código. Siga estes passos para debugar:

## 1. Abra o App com Console

1. Acesse: https://main.d3de0r2ujefnqj.amplifyapp.com
2. Login: `leanpsilva@gmail.com` / `Tifani%04`
3. Abra Developer Tools: **F12**
4. Vá para aba **Console**
5. **LIMPE** o console (cmd+K ou Control+L)

## 2. Crie 2 Sessões com Conteúdo Diferente

### Sessão A:
1. Clique "New Chat"
2. Envie mensagem: **"SESSÃO A - TESTE 1"**
3. Aguarde resposta
4. Envie: **"SESSÃO A - TESTE 2"**
5. Aguarde

Console deve mostrar logs como:
```
[ChatPage] Selecting session: [ID-A]
[ChatPage] Fetching session details...
[SessionService] Fetching session: [ID-A]
[SessionService] Got 2 messages for session [ID-A]
[ChatInterface] useEffect: initialMessages changed to 2 messages, sessionId=[ID-A]
```

### Sessão B:
1. Clique "New Chat" de novo
2. Envie: **"SESSÃO B - DIFERENTE 1"**
3. Aguarde resposta
4. Envie: **"SESSÃO B - DIFERENTE 2"**
5. Aguarde

## 3. Teste Switching - WATCH CONSOLE CAREFULLY

1. **Clique em "Sessão A"** no sidebar
2. **IMEDIATAMENTE olhe o console** - você deve ver:
   ```
   [ChatPage] Selecting session: [ID-A]
   [ChatPage] Fetching session details...
   [SessionService] Fetching session: [ID-A]
   [SessionService] Got 2 messages for session [ID-A]
   [SessionService] First message: "SESSÃO A - TESTE 1..."
   [ChatPage] Setting initialMessages with 2 items
   [ChatPage] Setting sessionId to: [ID-A]
   [ChatPage] State updated. Showing interface now...
   [ChatInterface] Mounted/Updated with sessionId: [ID-A], messages: 2
   [ChatInterface] useEffect: initialMessages changed to 2 messages, sessionId=[ID-A]
   ```

3. **Clique em "Sessão B"** no sidebar
4. **IMEDIATAMENTE olhe o console** - você deve ver:
   ```
   [ChatPage] Selecting session: [ID-B]
   [ChatPage] Fetching session details...
   [SessionService] Fetching session: [ID-B]
   [SessionService] Got 2 messages for session [ID-B]
   [SessionService] First message: "SESSÃO B - DIFERENTE 1..."
   [ChatPage] Setting initialMessages with 2 items
   [ChatPage] Setting sessionId to: [ID-B]
   [ChatPage] State updated. Showing interface now...
   [ChatInterface] Mounted/Updated with sessionId: [ID-B], messages: 2
   [ChatInterface] useEffect: initialMessages changed to 2 messages, sessionId=[ID-B]
   ```

## 4. O que procurar

### ✅ CERTO - Diferentes sessionIds:
```
[SessionService] Fetching session: abc123-A  ← ID da Sessão A
[SessionService] Fetching session: def456-B  ← ID DIFERENTE da Sessão B
```

### ❌ ERRADO - Mesmo sessionId:
```
[SessionService] Fetching session: abc123-A
[SessionService] Fetching session: abc123-A  ← MESMO ID!
```

### ✅ CERTO - Diferentes mensagens:
```
[SessionService] First message: "SESSÃO A - TESTE 1..."
[SessionService] First message: "SESSÃO B - DIFERENTE 1..."  ← DIFERENTE!
```

### ❌ ERRADO - Mesma mensagem:
```
[SessionService] First message: "SESSÃO A - TESTE 1..."
[SessionService] First message: "SESSÃO A - TESTE 1..."  ← MESMA!
```

### ✅ CERTO - initialMessages count muda:
```
[ChatInterface] useEffect: initialMessages changed to 2 messages, sessionId=abc123-A
[ChatInterface] useEffect: initialMessages changed to 2 messages, sessionId=def456-B
```

### ❌ ERRADO - initialMessages não muda ou fica igual:
```
[ChatInterface] useEffect: initialMessages changed to 2 messages, sessionId=abc123-A
// (nenhum output quando clica Sessão B)
```

## 5. Compare com Browser Display

Enquanto testa, TAMBÉM veja:
- **Esperado**: As mensagens no chat **MUDAM** quando clica diferentes sessões
- **Bug**: As mensagens no chat **NÃO MUDAM** ou ficam as mesmas

## 6. Reporte os Resultados

Copie e cole todo o console output (console.log) e me mande com:

1. **O que viu no console?** (Copie os logs principais)
2. **Os sessionIds mudaram?** (SIM/NÃO)
3. **As mensagens retornadas mudaram?** (SIM/NÃO)
4. **As mensagens no chat mudaram?** (SIM/NÃO)
5. **Algum erro em vermelho?** (SIM/NÃO - se SIM, copie o erro)

Com isso vou conseguir identificar EXATAMENTE onde o bug está!

---

## Se o console estiver cheio de logs

**Clique no ícone de lixeira** 🗑️ para limpar antes de cada teste.

Ou copie e execute para auto-limpar:

```javascript
// Cole isto no console para limpar
console.clear();
console.log('✅ Console limpo. Agora teste switching...');
```
