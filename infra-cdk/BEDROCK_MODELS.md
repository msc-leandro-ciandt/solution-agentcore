# Modelos Amazon Bedrock - JurisConsult

## 🤖 Modelo Atual

### Strands Agent (Padrão Configurado)

**Modelo**: `us.anthropic.claude-sonnet-4-5-20250929-v1:0`

- **Provedor**: Anthropic
- **Modelo**: Claude Sonnet 4.5
- **Versão**: 2025-09-29
- **Tipo**: Converse
- **Temperature**: 0.1 (muito determinístico, ideal para processos judiciais)
- **Localização**: us-east-1

**Características**:
- ✅ Excelente para análise de texto jurídico
- ✅ Preciso e confiável
- ✅ Rápido (ideal para respostas em tempo real)
- ✅ Suporta context windows grandes
- ✅ Custo-benefício otimizado

**Onde está configurado**:
```python
# patterns/strands-single-agent/basic_agent.py
bedrock_model = BedrockModel(
    model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0", temperature=0.1
)
```

---

## 📊 Comparação de Modelos Disponíveis

| Modelo | Velocidade | Custo | Qualidade | Contexto | Melhor Para |
|--------|-----------|--------|-----------|----------|------------|
| Claude 3 Haiku | ⚡⚡⚡ | $ | ⭐⭐ | 200k | Consultas simples |
| Claude 3.5 Sonnet | ⚡⚡ | $$ | ⭐⭐⭐⭐ | 200k | **Jurídico (ATUAL)** |
| Claude 3 Opus | ⚡ | $$$ | ⭐⭐⭐⭐⭐ | 200k | Análise complexa |

---

## 🔄 Alternativas de Modelos

Se quiser mudar o modelo, edite:
```yaml
# patterns/strands-single-agent/basic_agent.py
bedrock_model = BedrockModel(
    model_id="us.anthropic.claude-XXX",  # ← Mudar aqui
    temperature=0.1
)
```

### Opções Disponíveis:

```
# Claude 3.5 Sonnet (RECOMENDADO PARA JURÍDICO)
us.anthropic.claude-3-5-sonnet-20241022-v2:0

# Claude 3 Opus (Mais poderoso, mais caro)
us.anthropic.claude-3-opus-20240229-v1:0

# Claude 3 Haiku (Mais rápido, mais barato)
us.anthropic.claude-3-haiku-20240307-v1:0

# Llama 2 (Meta - alternativa open source)
us.meta.llama2-70b-chat-v1

# Llama 3.1 (Meta - mais novo)
us.meta.llama-3-1-70b-instruct-v1:0

# Mistral (Mistral AI)
us.mistral.mistral-7b-instruct-v0:2
```

---

## ⚙️ Configuração Atual

```python
# Temperatura (0 = determinístico, 1 = criativo)
temperature = 0.1  # Muito preciso (ideal para jurídico)

# Alternativas:
# temperature=0.3  # Mais criativo
# temperature=0.7  # Bem criativo
```

**Por que 0.1?** Para processos judiciais, precisamos:
- Respostas **consistentes** e **confiáveis**
- Minimizar alucinações
- Seguir com precisão as informações dos processos

---

## 💰 Custos Estimados (por 1M tokens)

| Modelo | Input | Output |
|--------|-------|--------|
| Haiku | $0.80 | $1.60 |
| **Sonnet 3.5** | **$3.00** | **$15.00** |
| Opus | $15.00 | $75.00 |

**Para JurisConsult**: Sonnet 3.5 tem melhor custo-benefício para análise jurídica.

---

## 🔧 Como Mudar o Modelo

### 1. Editar o arquivo do agente:
```bash
# Editar este arquivo
nano patterns/strands-single-agent/basic_agent.py

# Linha 87 - mudar model_id:
bedrock_model = BedrockModel(
    model_id="us.anthropic.claude-3-opus-20240229-v1:0",  # ← NOVO
    temperature=0.1
)
```

### 2. Fazer rebuild e deploy:
```bash
cd infra-cdk
npm run build
npx cdk deploy --all
```

### 3. Testar:
```bash
# Acessar interface e fazer uma query
https://main.d3de0r2ujefnqj.amplifyapp.com
```

---

## ✅ Recomendações para Processos Judiciais

### Modelo: Claude 3.5 Sonnet ✅ (ATUAL)
**Razões**:
- Excelente compreensão de texto legal
- Rápido (ideal para respostas em tempo real)
- Custo-benefício balanceado
- Contexto de 200k tokens (suficiente para documentos jurídicos)

### Alternativas:

**Se precisa de máxima qualidade:**
- Use Claude 3 Opus (mais caro, melhor)

**Se quer economizar:**
- Use Claude 3 Haiku (mais rápido, menos preciso)

---

## 📝 Próximos Passos

1. ✅ **Modelo atual está bom para começar**
2. Testar com casos reais
3. Ajustar temperatura se necessário
4. Avaliar custo vs qualidade após usar

---

**Modelo selecionado**: Claude Sonnet 4.5 (us.anthropic.claude-sonnet-4-5-20250929-v1:0)
**Status**: ✅ Pronto para processos judiciais
