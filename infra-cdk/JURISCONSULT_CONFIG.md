# JurisConsult - Configuração do Projeto

Sistema de consulta de processos judiciais para Leandro Pereira da Silva e Renata Hellen Garcia da Silva.

## Informações do Projeto

- **Nome do Projeto**: JurisConsult
- **Stack Base**: `juris-consult`
- **Agente**: JurisAgent
- **Padrão**: strands-single-agent
- **Tipo de Deployment**: Docker
- **Modo de Rede**: PUBLIC

## Usuários

### Admin - Leandro Pereira da Silva
- **Email**: leanpsilva@gmail.com
- **Role**: Admin (criado automaticamente)
- **Propósito**: Gerenciador do sistema

### Usuário - Renata Hellen Garcia da Silva
- **Email**: renatahellensouzagarcia@gmail.com
- **Role**: User (será criado via console ou API)
- **Propósito**: Consulta de processos pessoais

## Funcionalidades

O JurisAgent irá:
- Consultar processos judiciais pessoais
- Consultarmapeamento de processos por CPF/Nome
- Rastrear status de processos
- Fornecer informações sobre procedimentos judiciais
- Manter histórico de consultas seguras por usuário

## Próximos Passos

1. **Deploy da Infraestrutura**
   ```bash
   cd infra-cdk
   npm install
   npm run build
   npx cdk bootstrap  # Primeira vez apenas
   npx cdk deploy --all
   ```

2. **Criar usuário secundário (Renata)**
   - Via AWS Console: Cognito > User Pool > Users > Create User
   - Email: renatahellensouzagarcia@gmail.com
   - Ou via AWS CLI

3. **Configurar agente para consulta de processos**
   - Integrar com API de tribunal (CNJ, TJ-SP, etc.)
   - Configurar tools para busca de processos

## Segurança

- Usuários só podem consultar processos próprios
- Cada consulta é registrada e auditada
- Integração com Cognito para autenticação segura
- VPC pode ser ativado em produção (docs/DEPLOYMENT.md)

## Conta AWS

- **Account ID**: 455303857301
- **Usuário**: leandro (IAM user)
- **Região**: us-east-1

---

**Última atualização**: agosto/2026
