# Planejamento: Web Crawlers para TJRS e TJSC com AWS

## 1. Análise de Requisitos

### 1.1 Fontes de Dados

#### TJRS (Tribunal de Justiça do Rio Grande do Sul)
- **Portal Transparência**: https://transparencia.tjrs.jus.br/consulta_processual/
- **eProc**: Sistema eletrônico de processos
- **Diário da Justiça Eletrônico**: Comunicação de atos judiciais
- **Dados públicos**: Consulta por número de processo, nome de parte, CPF, OAB

#### TJSC (Tribunal de Justiça de Santa Catarina)
- **Consulta Pública**: https://eprocwebcon.tjsc.jus.br/consulta1g/
- **eProc**: Sistema eletrônico
- **Sessões do Tribunal**: https://www.tjsc.jus.br/web/judicial/sessoes-do-tribunal-de-justica
- **Serventias Extrajudiciais**: Consulta pública

### 1.2 Tipos de Dados a Capturar

```
- Informações de processos (número, partes, datas, status)
- Movimentações processuais (andamento, decisões)
- Dados de audiências/sessões
- Informações de comarcas e turmas
- Metadados de serventias
- Informações de juízes/desembargadores
```

### 1.3 Volumes Esperados

- **TJRS**: ~500k processos/ano
- **TJSC**: ~300k processos/ano
- **Total**: ~800k registros/ano
- **Frequência**: Diária/Semanal (atualizações)

---

## 2. Arquitetura AWS Proposta

### 2.1 Diagrama de Fluxo

```
┌─────────────────────────────────────────────────────────────┐
│                    FONTE DE DADOS                            │
│  TJRS Portal + TJSC Portal (Web)                              │
└────────────────────────┬────────────────────────────────────┘
                         │
         ┌───────────────┴──────────────────┐
         │                                   │
    ┌────▼────────┐              ┌──────────▼─────┐
    │ EventBridge │              │  Lambda Trigger│
    │ (Scheduler) │              │  (Webhooks)    │
    └────┬────────┘              └──────────┬─────┘
         │                                   │
         └───────────────┬───────────────────┘
                         │
         ┌───────────────▼────────────────┐
         │   Lambda - Web Crawler         │
         │  (Python + Selenium/Puppeteer) │
         │  - Parse HTML                  │
         │  - Extract data                │
         │  - Normalize fields            │
         └───────────────┬────────────────┘
                         │
    ┌────────────────────┼────────────────────┐
    │                    │                     │
┌───▼──────┐       ┌────▼─────┐        ┌─────▼────┐
│   SQS    │       │    S3     │        │ CloudWatch│
│ (Queue)  │       │ (Raw Data)│        │ (Logs)   │
└───┬──────┘       └────┬─────┘        └──────────┘
    │                    │
    └────────────┬───────┘
                 │
         ┌───────▼──────────┐
         │ Lambda - Parser  │
         │  - Clean data    │
         │  - Validate      │
         │  - Deduplicate   │
         └────────┬─────────┘
                  │
      ┌───────────┼──────────────┐
      │           │              │
┌─────▼────┐ ┌────▼──────┐ ┌────▼──────┐
│ DynamoDB │ │ RDS/Aurora│ │ OpenSearch│
│  (NoSQL) │ │ (SQL)     │ │ (Full-text)│
└──────────┘ └───────────┘ └───────────┘
      │           │              │
      └───────────┼──────────────┘
                  │
         ┌────────▼────────┐
         │  API Gateway    │
         │  + Lambda Proxy │
         └────────┬────────┘
                  │
         ┌────────▼────────┐
         │   Frontend      │
         │   React App     │
         └─────────────────┘
```

### 2.2 Componentes Detalhados

#### **Lambda 1: Web Crawler** (Python 3.11)
```
Nome: tjrs-tjsc-crawler
Memória: 3008 MB
Timeout: 900s (15 min)
Camada: Chromium (headless browser)
Triggers:
  - EventBridge (diário 2AM UTC)
  - SQS (para chamadas sob demanda)
  - API Gateway (webhook)
```

**Responsabilidades:**
- Acesso aos portais TJRS/TJSC
- Navegação via Selenium/Puppeteer
- Extração de dados HTML
- Upload para S3 (raw data)
- Envio de mensagens para SQS (processadas)

#### **Lambda 2: Data Parser** (Python 3.11)
```
Nome: tjrs-tjsc-parser
Memória: 1024 MB
Timeout: 300s
Trigger: SQS (batch de 10)
```

**Responsabilidades:**
- Parse de dados brutos
- Limpeza e normalização
- Validação contra schema
- Deduplicação
- Inserção em DB

#### **Lambda 3: API Handler** (Node.js 18)
```
Nome: tjrs-tjsc-api
Memória: 512 MB
Timeout: 30s
Trigger: API Gateway
```

**Endpoints:**
- `GET /processes/search?number=<num>&court=<court>`
- `GET /processes/{processId}`
- `GET /movements/{processId}`
- `GET /courts`
- `POST /crawler/trigger` (admin)

---

## 3. Arquitetura de Data Lake

### 3.1 Estrutura S3

```
s3://tjrs-tjsc-datalake/
├── raw/
│   ├── tjrs/
│   │   ├── 2026/01/15/
│   │   │   ├── processes_batch_1.html
│   │   │   ├── movements_batch_1.html
│   │   └── ...
│   └── tjsc/
│       └── 2026/01/15/
├── processed/
│   ├── tjrs/
│   │   ├── processes/
│   │   │   └── 2026/01/15/
│   │   │       └── processes_batch_1.parquet
│   │   └── movements/
│   └── tjsc/
├── archive/
│   ├── failed_crawls/
│   └── error_logs/
└── metadata/
    ├── schemas/
    ├── dictionaries/
    └── audit_logs/
```

### 3.2 Armazenamento de Dados

#### **DynamoDB (Primary)**
```
Table: ProcessMetadata
PK: ProcessId (e.g., "0000001-23.2025.8.26.0100")
SK: CourtCode#Version (e.g., "TJRS#20260115T020000Z")

Attributes:
{
  "ProcessId": "0000001-23.2025.8.26.0100",
  "CourtCode": "TJRS",
  "ProcessNumber": "0000001-23.2025.8.26.0100",
  "Status": "PENDENTE",
  "PlaintiffName": "João Silva",
  "DefendantName": "Maria Santos",
  "CreatedAt": "2025-01-15T02:00:00Z",
  "UpdatedAt": "2026-08-17T10:30:00Z",
  "LastCrawledAt": "2026-08-17T10:30:00Z",
  "DataSourceUrl": "https://transparencia.tjrs.jus.br/...",
  "RawDataS3Path": "s3://bucket/raw/tjrs/2026/01/15/...",
  "TTL": 1735689600  // 30 dias
}
```

#### **RDS Aurora PostgreSQL (Secondary - Analytics)**
```
Schema:
- processes (PK: id, UK: process_number)
- process_movements (FK: process_id)
- parties (FK: process_id)
- judges (PK: id)
- courts (PK: id)
- audit_log (all changes)
```

**Vantagens:**
- Queries SQL complexas
- Full ACID transactions
- Relatórios/Analytics
- Integração com BI tools

#### **OpenSearch (Busca)**
```
Index: processes-{YYYY.MM.DD}
Mapping:
{
  "properties": {
    "processId": { "type": "keyword" },
    "processNumber": { "type": "keyword" },
    "plaintiffName": { "type": "text", "analyzer": "standard" },
    "defendantName": { "type": "text" },
    "courtCode": { "type": "keyword" },
    "status": { "type": "keyword" },
    "createdAt": { "type": "date" },
    "updatedAt": { "type": "date" }
  }
}
```

**Vantagens:**
- Busca full-text rápida
- Filtros por facets
- Autocomplete
- Relevância por score

---

## 4. Implementação Detalhada

### 4.1 Crawler Lambda - Pseudocódigo

```python
import boto3
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from datetime import datetime
import json
import hashlib

logger = logging.getLogger()

class TJRSCrawler:
    def __init__(self):
        self.s3 = boto3.client('s3')
        self.sqs = boto3.client('sqs')
        self.cloudwatch = boto3.client('cloudwatch')
        self.bucket = 'tjrs-tjsc-datalake'
    
    def setup_browser(self):
        """Inicia Chromium headless"""
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        return webdriver.Chrome(options=options)
    
    def crawl_process(self, process_number):
        """Crawla um processo específico"""
        driver = self.setup_browser()
        try:
            url = f"https://transparencia.tjrs.jus.br/consulta_processual/?numero={process_number}"
            driver.get(url)
            
            # Aguarda carregamento
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "processo-header"))
            )
            
            # Extrai dados
            html_content = driver.page_source
            
            # Armazena raw data
            timestamp = datetime.utcnow().isoformat()
            s3_key = f"raw/tjrs/{datetime.now().strftime('%Y/%m/%d')}/process_{process_number}_{timestamp}.html"
            
            self.s3.put_object(
                Bucket=self.bucket,
                Key=s3_key,
                Body=html_content,
                ContentType='text/html'
            )
            
            # Envia para fila de processamento
            self.sqs.send_message(
                QueueUrl=os.environ['SQS_QUEUE_URL'],
                MessageBody=json.dumps({
                    'processNumber': process_number,
                    'courtCode': 'TJRS',
                    's3Path': s3_key,
                    'timestamp': timestamp
                })
            )
            
            return {'status': 'success', 's3Path': s3_key}
            
        except Exception as e:
            logger.error(f"Error crawling {process_number}: {str(e)}")
            self.cloudwatch.put_metric_data(
                Namespace='TJCrawler',
                MetricData=[{
                    'MetricName': 'CrawlErrors',
                    'Value': 1,
                    'Unit': 'Count'
                }]
            )
            raise
        finally:
            driver.quit()

def lambda_handler(event, context):
    crawler = TJRSCrawler()
    
    # Determina fonte de eventos
    if 'Records' in event:  # SQS
        for record in event['Records']:
            message = json.loads(record['body'])
            process_number = message['processNumber']
    else:  # EventBridge/API
        # Busca lista de processos a crawlar
        # (implementar lógica de descoberta)
        pass
    
    return {'statusCode': 200, 'body': 'Crawl started'}
```

### 4.2 Parser Lambda - Pseudocódigo

```python
import boto3
import json
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime

class ProcessParser:
    def __init__(self):
        self.s3 = boto3.client('s3')
        self.dynamodb = boto3.resource('dynamodb')
        self.rds = boto3.client('rds-data')
        self.table = self.dynamodb.Table('ProcessMetadata')
    
    def parse_tjrs_process(self, html_content):
        """Parse específico para TJRS"""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Extrai campos específicos
        process_data = {
            'processNumber': self._extract_field(soup, '.processo-numero'),
            'status': self._extract_field(soup, '.status'),
            'plaintiffName': self._extract_field(soup, '.autor'),
            'defendantName': self._extract_field(soup, '.réu'),
            'filingDate': self._extract_date(soup, '.data-distribuição'),
            'courtCode': 'TJRS',
            'lastUpdate': datetime.utcnow().isoformat()
        }
        
        # Valida contra schema
        self._validate_schema(process_data)
        
        return process_data
    
    def save_to_dynamodb(self, process_data):
        """Salva em DynamoDB"""
        process_id = process_data['processNumber']
        
        self.table.put_item(
            Item={
                'ProcessId': process_id,
                'CourtCode#Version': f"{process_data['courtCode']}#{datetime.utcnow().isoformat()}",
                **process_data,
                'TTL': int((datetime.utcnow().timestamp()) + 30*24*60*60)  # 30 dias
            }
        )
    
    def save_to_rds(self, process_data):
        """Salva em RDS para analytics"""
        query = """
        INSERT INTO processes (process_number, status, plaintiff_name, 
                              defendant_name, filing_date, court_code, updated_at)
        VALUES (:processNumber, :status, :plaintiffName, :defendantName, 
                :filingDate, :courtCode, :lastUpdate)
        ON CONFLICT (process_number) DO UPDATE SET
            status = EXCLUDED.status,
            updated_at = EXCLUDED.updated_at
        """
        
        self.rds.execute_statement(
            resourceArn=os.environ['RDS_ARN'],
            secretArn=os.environ['RDS_SECRET_ARN'],
            database='tjcrawler',
            sql=query,
            parameters=[
                {'name': key, 'value': {'stringValue': str(val)}}
                for key, val in process_data.items()
            ]
        )

def lambda_handler(event, context):
    parser = ProcessParser()
    
    for record in event['Records']:
        message = json.loads(record['body'])
        
        # Baixa raw data do S3
        raw_data = parser.s3.get_object(
            Bucket='tjrs-tjsc-datalake',
            Key=message['s3Path']
        )
        html_content = raw_data['Body'].read()
        
        # Parse
        if message['courtCode'] == 'TJRS':
            process_data = parser.parse_tjrs_process(html_content)
        
        # Salva em ambos DBs
        parser.save_to_dynamodb(process_data)
        parser.save_to_rds(process_data)
    
    return {'statusCode': 200}
```

---

## 5. Estratégia de Crawling

### 5.1 Descoberta de Processos

**Opção 1: Crawl Incremental**
- Busca processos novos/atualizados desde último crawl
- Mais eficiente
- Requer API ou padrão previsível

**Opção 2: Bulk Crawl Periódico**
- Crawla todos os processos em intervalo (semanal)
- Mais robusto
- Maior volume

**Opção 3: Busca por Intervalo de Números**
- Incrementa processo number (CNJ format)
- Combina com ambos acima

### 5.2 Implementação Recomendada

```python
# Estratégia Híbrida

# 1. Daily - Processos últimas 24h (incremental)
EventBridge(daily 2AM) → Lambda → Crawl recent processes

# 2. Weekly - Todos os processos TJRS (bulk)
EventBridge(weekly Sunday 1AM) → Lambda → Crawl all TJRS

# 3. Weekly - Todos os processos TJSC (bulk)
EventBridge(weekly Sunday 3AM) → Lambda → Crawl all TJSC

# 4. On-demand - API
API Gateway POST /crawler/process/{number} → Lambda → Crawl single
```

---

## 6. Gestão de Limitações e Respeito aos Portais

### 6.1 Throttling e Rate Limiting

```python
class RespectfulCrawler:
    def __init__(self):
        self.delay_between_requests = 2  # segundos
        self.max_concurrent_connections = 3
        self.user_agent = "TJRS-TJSC-Bot/1.0 (+http://company.com/bot)"
    
    def crawl_with_delay(self):
        time.sleep(self.delay_between_requests)
        # ... crawler logic
    
    def respect_robots_txt(self):
        """Respeita robots.txt dos portais"""
        # Check robots.txt before crawling
        pass
```

### 6.2 Monitoramento e Alertas

```
CloudWatch Metrics:
- CrawlErrors: Erros de crawl
- RequestBlockedCount: Requisições bloqueadas (429, 403)
- AverageCrawlTime: Tempo médio por processo
- DataQualityScore: % de dados válidos

Alertas:
- ErrorRate > 5% → SNS notification
- RequestBlocked > 10 → Pause crawler
- CrawlTime > 30s → Investigate
```

---

## 7. Otimizações de Custo

### 7.1 Estimativa de Custos Mensais

| Serviço | Uso | Custo |
|---------|-----|-------|
| Lambda | 2M invocações | $40 |
| DynamoDB | 1M writes/day | $100 |
| RDS Aurora | db.t3.small | $60 |
| S3 | 100GB storage | $2.30 |
| SQS | 10M msgs/month | $5 |
| CloudWatch | Logs/Metrics | $20 |
| **Total** | | **~$230/mês** |

### 7.2 Estratégias para Reduzir Custos

1. **DynamoDB**: Use on-demand + TTL de 30 dias
2. **RDS**: Use Read Replicas para analytics
3. **S3**: Lifecycle policy (Archive after 90 days)
4. **Lambda**: Otimizar memória vs tempo de execução

---

## 8. Compliance e Conformidade

### 8.1 Considerações Legais

- ✅ Dados são públicos (TJRS/TJSC disponibilizam)
- ✅ Respeitar ToS dos portais
- ✅ Rate limiting (não sobrecarregar)
- ✅ Logs de auditoria (quem acessou, quando)
- ⚠️ Verificar LGPD (dados pessoais de partes)

### 8.2 Segurança

```
- Encriptação em trânsito (TLS 1.2+)
- Encriptação em repouso (KMS)
- IAM roles com least privilege
- VPC endpoints (S3, DynamoDB)
- Audit logging (CloudTrail)
```

---

## 9. Roadmap de Implementação

### Fase 1: MVP (2-3 semanas)
- [ ] Setup infraestrutura AWS (VPC, IAM, buckets)
- [ ] Lambda crawler básica (TJRS apenas)
- [ ] DynamoDB + S3 storage
- [ ] API Gateway + Lambda proxy

### Fase 2: Expansão (2 semanas)
- [ ] Adicionar TJSC
- [ ] RDS Aurora + sync
- [ ] OpenSearch indexing
- [ ] Melhorar parser (movimentações)

### Fase 3: Produção (2 semanas)
- [ ] Monitoring + alertas
- [ ] Error handling + retry logic
- [ ] Performance tuning
- [ ] Documentação

### Fase 4: Otimização (ongoing)
- [ ] Incremental crawling
- [ ] ML para deduplicação
- [ ] Full-text search enhancements

---

## 10. Próximos Passos

### 10.1 Ação Imediata

1. **Validar acesso aos portais**
   ```bash
   curl -I https://transparencia.tjrs.jus.br/consulta_processual/
   curl -I https://eprocwebcon.tjsc.jus.br/consulta1g/
   ```

2. **Revisar ToS e robots.txt**
   - TJRS: https://transparencia.tjrs.jus.br/robots.txt
   - TJSC: https://www.tjsc.jus.br/robots.txt

3. **Criar repositório CDK**
   ```bash
   cdk init app --language python
   # Adicionar resources (Lambda, DynamoDB, RDS, etc)
   ```

4. **Prototipar parser**
   - Baixar sample HTML dos portais
   - Testar BeautifulSoup/Scrapy
   - Definir schema de dados

### 10.2 Contatos para Esclarecimentos

- **TJRS Suporte**: (51) 3210-6500
- **TJSC Suporte**: Verificar site
- **Consultar se existe API oficial antes de scraping**

---

## 11. Referências

- [AWS Lambda for Web Scraping](https://docs.aws.amazon.com/lambda/)
- [Selenium on Lambda](https://github.com/serverless-chrome/serverless-chrome)
- [DynamoDB Best Practices](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/)
- [AWS RDS Aurora](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Aurora.html)
- [OpenSearch Documentation](https://opensearch.org/docs/)
