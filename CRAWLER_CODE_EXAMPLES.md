# Exemplos de Código Prontos para Usar - Web Crawlers TJRS/TJSC

Este documento contém exemplos funcionais de código para iniciar sua implementação.

---

## 1. Lambda Crawler - TJRS

**Arquivo**: `lambdas/crawler/index.py`

```python
import json
import boto3
import logging
import os
import time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client('s3')
sqs_client = boto3.client('sqs')
cloudwatch_client = boto3.client('cloudwatch')

# Environment variables
DATALAKE_BUCKET = os.environ['DATALAKE_BUCKET']
SQS_QUEUE_URL = os.environ['SQS_QUEUE_URL']
DYNAMODB_TABLE = os.environ['DYNAMODB_TABLE']

class TJRSCrawler:
    """Crawler para TJRS Portal Transparência"""
    
    def __init__(self):
        self.base_url = "https://transparencia.tjrs.jus.br/consulta_processual/"
        self.delay_between_requests = 2  # segundos
        self.max_retries = 3
        self.timeout = 30
    
    def setup_chrome_driver(self):
        """Configura e retorna Chrome WebDriver"""
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--user-agent=TJRS-Crawler/1.0")
        
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(self.timeout)
        return driver
    
    def crawl_process(self, process_number):
        """Faz crawl de um processo específico"""
        driver = None
        try:
            driver = self.setup_chrome_driver()
            
            # Monta URL com query
            search_url = f"{self.base_url}?numero={process_number}"
            logger.info(f"Crawling: {search_url}")
            
            # Acessa página
            driver.get(search_url)
            
            # Aguarda carregamento da página
            WebDriverWait(driver, self.timeout).until(
                EC.presence_of_element_located((By.CLASS_NAME, "processo-header"))
            )
            
            # Aguarda estabilização
            time.sleep(2)
            
            # Extrai HTML completo
            html_content = driver.page_source
            
            # Salva no S3
            timestamp = datetime.utcnow().isoformat()
            s3_key = self._save_raw_to_s3(process_number, html_content, timestamp)
            
            # Envia para SQS para processamento
            self._send_to_sqs(process_number, 'TJRS', s3_key, timestamp)
            
            logger.info(f"Successfully crawled {process_number}")
            self._send_metric('CrawlSuccess', 1)
            
            return {
                'status': 'success',
                'processNumber': process_number,
                's3Path': s3_key
            }
        
        except Exception as e:
            logger.error(f"Error crawling {process_number}: {str(e)}")
            self._send_metric('CrawlErrors', 1)
            raise
        
        finally:
            if driver:
                driver.quit()
    
    def _save_raw_to_s3(self, process_number, html_content, timestamp):
        """Salva HTML bruto no S3"""
        date_path = datetime.fromisoformat(timestamp).strftime('%Y/%m/%d')
        s3_key = f"raw/tjrs/{date_path}/process_{process_number}_{timestamp}.html"
        
        s3_client.put_object(
            Bucket=DATALAKE_BUCKET,
            Key=s3_key,
            Body=html_content.encode('utf-8'),
            ContentType='text/html',
            ServerSideEncryption='AES256'
        )
        
        logger.info(f"Saved to S3: {s3_key}")
        return s3_key
    
    def _send_to_sqs(self, process_number, court_code, s3_path, timestamp):
        """Envia mensagem para SQS para processamento"""
        message = {
            'processNumber': process_number,
            'courtCode': court_code,
            's3Path': s3_path,
            'timestamp': timestamp,
            'source': 'crawler',
            'status': 'raw'
        }
        
        sqs_client.send_message(
            QueueUrl=SQS_QUEUE_URL,
            MessageBody=json.dumps(message),
            MessageGroupId='tjrs'  # Se FIFO
        )
        
        logger.info(f"Message sent to SQS for {process_number}")
    
    def _send_metric(self, metric_name, value):
        """Envia métrica para CloudWatch"""
        cloudwatch_client.put_metric_data(
            Namespace='TJCrawler',
            MetricData=[{
                'MetricName': metric_name,
                'Value': value,
                'Unit': 'Count',
                'Timestamp': datetime.utcnow()
            }]
        )
    
    def crawl_batch(self, process_numbers):
        """Crawla múltiplos processos"""
        results = []
        for process_number in process_numbers:
            try:
                result = self.crawl_process(process_number)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to crawl {process_number}: {str(e)}")
                results.append({
                    'status': 'failed',
                    'processNumber': process_number,
                    'error': str(e)
                })
            
            # Respeita rate limit
            time.sleep(self.delay_between_requests)
        
        return results


def lambda_handler(event, context):
    """Lambda handler principal"""
    logger.info(f"Event: {json.dumps(event)}")
    
    crawler = TJRSCrawler()
    
    try:
        # Determina fonte de eventos
        if 'Records' in event:
            # SQS trigger
            process_numbers = [
                json.loads(record['body'])['processNumber']
                for record in event['Records']
            ]
        elif 'processNumbers' in event:
            # Direct invocation
            process_numbers = event['processNumbers']
        else:
            # EventBridge - busca processos recentes
            logger.info("EventBridge trigger - searching for recent processes")
            # TODO: Implementar lógica de descoberta automática
            process_numbers = []
        
        # Faz crawl
        results = crawler.crawl_batch(process_numbers)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Crawl completed',
                'results': results,
                'totalProcessed': len(results),
                'successCount': sum(1 for r in results if r['status'] == 'success')
            })
        }
    
    except Exception as e:
        logger.error(f"Lambda error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }


# Para testes locais
if __name__ == "__main__":
    import os
    os.environ['DATALAKE_BUCKET'] = 'test-bucket'
    os.environ['SQS_QUEUE_URL'] = 'https://sqs.us-east-1.amazonaws.com/123456789/test-queue'
    os.environ['DYNAMODB_TABLE'] = 'ProcessMetadata'
    
    # Testa com um processo fictício
    result = lambda_handler({
        'processNumbers': ['0000001-23.2025.8.26.0100']
    }, None)
    print(json.dumps(result, indent=2))
```

---

## 2. Lambda Parser

**Arquivo**: `lambdas/parser/index.py`

```python
import json
import boto3
import logging
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import re

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client('s3')
dynamodb_client = boto3.client('dynamodb')

DATALAKE_BUCKET = boto3.client('s3')
DYNAMODB_TABLE = 'ProcessMetadata'

class TJRSParser:
    """Parser para dados TJRS"""
    
    def __init__(self):
        self.schema = {
            'processNumber': str,
            'courtCode': str,
            'status': str,
            'plaintiffName': str,
            'defendantName': str,
        }
    
    def parse_html(self, html_content):
        """Parse do HTML da TJRS"""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        data = {
            'courtCode': 'TJRS',
            'rawData': html_content[:1000],  # Store snippet
            'parsedAt': datetime.utcnow().isoformat()
        }
        
        try:
            # Extrai número do processo
            process_elem = soup.find('span', class_='processo-numero')
            if process_elem:
                data['processNumber'] = process_elem.text.strip()
            
            # Extrai status
            status_elem = soup.find('span', class_='status')
            if status_elem:
                data['status'] = status_elem.text.strip()
            
            # Extrai partes
            plaintiff_elem = soup.find('td', {'header': 'Autor'})
            if plaintiff_elem:
                data['plaintiffName'] = plaintiff_elem.text.strip()
            
            defendant_elem = soup.find('td', {'header': 'Réu'})
            if defendant_elem:
                data['defendantName'] = defendant_elem.text.strip()
            
            # Extrai datas
            filing_elem = soup.find('span', class_='data-distribuição')
            if filing_elem:
                date_str = filing_elem.text.strip()
                data['filingDate'] = self._parse_date(date_str)
            
            # Extrai movimentações
            data['movements'] = self._extract_movements(soup)
            
            return data
        
        except Exception as e:
            logger.error(f"Parse error: {str(e)}")
            raise
    
    def _extract_movements(self, soup):
        """Extrai movimentações do processo"""
        movements = []
        
        movements_table = soup.find('table', class_='movimentacoes')
        if not movements_table:
            return movements
        
        rows = movements_table.find_all('tr')[1:]  # Skip header
        
        for row in rows:
            cols = row.find_all('td')
            if len(cols) >= 3:
                movement = {
                    'date': cols[0].text.strip(),
                    'type': cols[1].text.strip(),
                    'description': cols[2].text.strip(),
                }
                movements.append(movement)
        
        return movements
    
    def _parse_date(self, date_str):
        """Converte string de data para ISO format"""
        try:
            # Tenta vários formatos
            for fmt in ['%d/%m/%Y', '%d.%m.%Y', '%Y-%m-%d']:
                try:
                    dt = datetime.strptime(date_str, fmt)
                    return dt.isoformat()
                except ValueError:
                    continue
            return date_str
        except:
            return date_str
    
    def validate_data(self, data):
        """Valida dados contra schema"""
        required_fields = ['processNumber', 'courtCode']
        
        for field in required_fields:
            if field not in data or not data[field]:
                raise ValueError(f"Missing required field: {field}")
        
        return True
    
    def save_to_dynamodb(self, data):
        """Salva em DynamoDB"""
        try:
            # Prepara item
            item = {
                'ProcessId': {'S': data['processNumber']},
                'CourtCode': {'S': data['courtCode']},
                'Status': {'S': data.get('status', 'UNKNOWN')},
                'PlaintiffName': {'S': data.get('plaintiffName', '')},
                'DefendantName': {'S': data.get('defendantName', '')},
                'UpdatedAt': {'S': datetime.utcnow().isoformat()},
                'LastCrawledAt': {'S': data.get('parsedAt', '')},
                'TTL': {'N': str(int((datetime.utcnow() + timedelta(days=30)).timestamp()))}
            }
            
            if 'filingDate' in data:
                item['FilingDate'] = {'S': data['filingDate']}
            
            if data.get('movements'):
                item['MovementCount'] = {'N': str(len(data['movements']))}
            
            # Put item
            dynamodb_client.put_item(
                TableName=DYNAMODB_TABLE,
                Item=item
            )
            
            logger.info(f"Saved to DynamoDB: {data['processNumber']}")
            return True
        
        except Exception as e:
            logger.error(f"DynamoDB save error: {str(e)}")
            raise


def lambda_handler(event, context):
    """Handler para SQS trigger"""
    logger.info(f"Event: {json.dumps(event)}")
    
    parser = TJRSParser()
    results = []
    
    try:
        # Processa cada mensagem SQS
        for record in event.get('Records', []):
            try:
                # Parse mensagem
                message = json.loads(record['body'])
                process_number = message['processNumber']
                s3_path = message['s3Path']
                court_code = message['courtCode']
                
                logger.info(f"Processing: {process_number} from {s3_path}")
                
                # Baixa HTML do S3
                s3_response = s3_client.get_object(
                    Bucket=DATALAKE_BUCKET,
                    Key=s3_path
                )
                html_content = s3_response['Body'].read().decode('utf-8')
                
                # Parse
                data = parser.parse_html(html_content)
                
                # Valida
                parser.validate_data(data)
                
                # Salva
                parser.save_to_dynamodb(data)
                
                results.append({
                    'status': 'success',
                    'processNumber': process_number,
                    'movements': len(data.get('movements', []))
                })
            
            except Exception as e:
                logger.error(f"Error processing record: {str(e)}")
                results.append({
                    'status': 'failed',
                    'error': str(e)
                })
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Batch processed',
                'results': results,
                'successCount': sum(1 for r in results if r['status'] == 'success')
            })
        }
    
    except Exception as e:
        logger.error(f"Lambda error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
```

---

## 3. API Lambda - Query Handler

**Arquivo**: `lambdas/api/index.py`

```python
import json
import boto3
import logging
from decimal import Decimal

logger = logging.getLogger()

dynamodb_client = boto3.client('dynamodb')
DYNAMODB_TABLE = 'ProcessMetadata'

class DecimalEncoder(json.JSONEncoder):
    """Helper para serializar Decimal do DynamoDB"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


def query_by_process_number(process_number):
    """Query por número do processo"""
    try:
        response = dynamodb_client.get_item(
            TableName=DYNAMODB_TABLE,
            Key={
                'ProcessId': {'S': process_number},
                'CourtCode': {'S': 'TJRS'}  # TODO: passar como param
            }
        )
        
        if 'Item' not in response:
            return None
        
        return response['Item']
    
    except Exception as e:
        logger.error(f"Query error: {str(e)}")
        raise


def query_by_court_and_date(court_code, start_date, end_date):
    """Query por corte e intervalo de datas"""
    try:
        response = dynamodb_client.query(
            TableName=DYNAMODB_TABLE,
            IndexName='CourtCodeUpdatedAtIndex',
            KeyConditionExpression='CourtCode = :court AND UpdatedAt BETWEEN :start AND :end',
            ExpressionAttributeValues={
                ':court': {'S': court_code},
                ':start': {'S': start_date},
                ':end': {'S': end_date}
            },
            Limit=100
        )
        
        return response.get('Items', [])
    
    except Exception as e:
        logger.error(f"Query error: {str(e)}")
        raise


def lambda_handler(event, context):
    """API Gateway handler"""
    logger.info(f"Event: {json.dumps(event)}")
    
    try:
        # Parse requisição
        path = event['path']
        method = event['httpMethod']
        query_params = event.get('queryStringParameters', {})
        
        # Routes
        if path == '/processes' and method == 'GET':
            # Busca por número de processo
            process_number = query_params.get('number')
            
            if not process_number:
                return {
                    'statusCode': 400,
                    'body': json.dumps({'error': 'Missing parameter: number'})
                }
            
            result = query_by_process_number(process_number)
            
            if not result:
                return {
                    'statusCode': 404,
                    'body': json.dumps({'error': 'Process not found'})
                }
            
            return {
                'statusCode': 200,
                'body': json.dumps(result, cls=DecimalEncoder),
                'headers': {'Content-Type': 'application/json'}
            }
        
        elif path == '/processes/search' and method == 'GET':
            # Busca por corte e data
            court_code = query_params.get('court', 'TJRS')
            start_date = query_params.get('start', '2026-01-01')
            end_date = query_params.get('end', '2026-12-31')
            
            results = query_by_court_and_date(court_code, start_date, end_date)
            
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'count': len(results),
                    'items': results
                }, cls=DecimalEncoder),
                'headers': {'Content-Type': 'application/json'}
            }
        
        else:
            return {
                'statusCode': 404,
                'body': json.dumps({'error': 'Route not found'})
            }
    
    except Exception as e:
        logger.error(f"Handler error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
```

---

## 4. Requirements.txt

**Arquivo**: `requirements.txt`

```
boto3==1.28.50
botocore==1.31.50
selenium==4.13.0
beautifulsoup4==4.12.2
lxml==4.9.3
aws-lambda-powertools==2.26.0
```

---

## 5. Testes Locais

**Arquivo**: `test_crawler.py`

```python
import unittest
from unittest.mock import patch, MagicMock
import json

# Assuming crawler code is in crawler.py
from crawler import TJRSCrawler, lambda_handler


class TestTJRSCrawler(unittest.TestCase):
    
    def setUp(self):
        self.crawler = TJRSCrawler()
    
    @patch('crawler.webdriver.Chrome')
    @patch('crawler.s3_client')
    @patch('crawler.sqs_client')
    def test_crawl_process_success(self, mock_sqs, mock_s3, mock_chrome):
        """Test successful process crawl"""
        # Mock WebDriver
        mock_driver = MagicMock()
        mock_chrome.return_value = mock_driver
        mock_driver.page_source = "<html>Test HTML</html>"
        
        # Run crawl
        result = self.crawler.crawl_process("0000001-23.2025.8.26.0100")
        
        # Assertions
        self.assertEqual(result['status'], 'success')
        self.assertIn('0000001-23.2025.8.26.0100', result['processNumber'])
        
        # Verify S3 and SQS were called
        mock_s3.put_object.assert_called_once()
        mock_sqs.send_message.assert_called_once()
    
    @patch('crawler.webdriver.Chrome')
    def test_crawl_process_timeout(self, mock_chrome):
        """Test timeout handling"""
        mock_driver = MagicMock()
        mock_chrome.return_value = mock_driver
        mock_driver.get.side_effect = TimeoutError("Page load timeout")
        
        with self.assertRaises(Exception):
            self.crawler.crawl_process("0000001-23.2025.8.26.0100")


class TestParser(unittest.TestCase):
    
    def test_parse_html_valid(self):
        """Test HTML parsing"""
        from parser import TJRSParser
        
        parser = TJRSParser()
        
        html = """
        <html>
            <span class="processo-numero">0000001-23.2025.8.26.0100</span>
            <span class="status">PENDENTE</span>
        </html>
        """
        
        result = parser.parse_html(html)
        
        self.assertEqual(result['processNumber'], '0000001-23.2025.8.26.0100')
        self.assertEqual(result['status'], 'PENDENTE')


if __name__ == '__main__':
    unittest.main()
```

---

## 6. Makefile para Deploy

**Arquivo**: `Makefile`

```makefile
.PHONY: help deploy test lint clean

help:
	@echo "TJRS/TJSC Crawler - Available commands:"
	@echo "  make test      - Run unit tests"
	@echo "  make lint      - Run code linting"
	@echo "  make deploy    - Deploy to AWS"
	@echo "  make clean     - Clean build artifacts"

test:
	python -m pytest lambdas/ -v

lint:
	pylint lambdas/

deploy:
	cdk deploy --require-approval=never

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf dist/ build/ *.egg-info
```

---

## 7. Docker para Local Development

**Arquivo**: `Dockerfile`

```dockerfile
FROM public.ecr.aws/lambda/python:3.11

# Install system dependencies for Selenium
RUN yum install -y \
    chromium-browser \
    chromedriver

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install -r requirements.txt

# Copy crawler code
COPY lambdas/crawler/ ${LAMBDA_TASK_ROOT}/

# Set handler
CMD [ "index.lambda_handler" ]
```

---

## 8. Exemplo de Uso da API

```bash
# Query por número do processo
curl -X GET "https://api.example.com/processes?number=0000001-23.2025.8.26.0100"

# Response:
{
  "ProcessId": "0000001-23.2025.8.26.0100",
  "CourtCode": "TJRS",
  "Status": "PENDENTE",
  "PlaintiffName": "João Silva",
  "DefendantName": "Maria Santos",
  "UpdatedAt": "2026-08-17T10:30:00",
  "MovementCount": 5
}

# Busca por corte e data
curl -X GET "https://api.example.com/processes/search?court=TJRS&start=2026-01-01&end=2026-12-31"
```

---

## ✅ Próximas Ações

1. **Copiar arquivos para seu projeto**
2. **Instalar dependências**: `pip install -r requirements.txt`
3. **Testar localmente**: `python -m pytest`
4. **Deploy**: `make deploy`

---

*Estes exemplos são starting points. Ajuste conforme seus requisitos específicos.*
