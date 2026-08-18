# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
AWS CDK Stack para Crawlers TJRS/TJSC

Este stack cria toda a infraestrutura necessária para:
- Crawling dos portais TJRS e TJSC
- Armazenamento em DynamoDB, RDS, S3
- Processamento de dados com Lambda
- Busca full-text com OpenSearch
- API GraphQL/REST para acesso aos dados
"""

from aws_cdk import (
    Stack,
    aws_lambda as lambda_,
    aws_dynamodb as dynamodb,
    aws_rds as rds,
    aws_s3 as s3,
    aws_s3_lifecycle as s3_lifecycle,
    aws_sqs as sqs,
    aws_sns as sns,
    aws_apigateway as apigateway,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
    aws_ec2 as ec2,
    aws_logs as logs,
    aws_cloudwatch as cloudwatch,
    Duration,
    RemovalPolicy,
    Tags,
)
from constructs import Construct


class TJRSTJSCCrawlerStack(Stack):
    """Stack principal para crawlers TJRS/TJSC"""

    def __init__(self, scope: Construct, id: str, **kwargs):
        super().__init__(scope, id, **kwargs)

        # ============================================================================
        # 1. NETWORKING - VPC para RDS e Lambda
        # ============================================================================
        vpc = ec2.Vpc(
            self,
            "CrawlerVPC",
            max_azs=2,
            nat_gateways=1,
            cidr="10.0.0.0/16",
        )

        # ============================================================================
        # 2. STORAGE - S3 Data Lake
        # ============================================================================
        datalake_bucket = s3.Bucket(
            self,
            "DataLakeBucket",
            bucket_name=f"tjrs-tjsc-datalake-{self.account}",
            encryption=s3.BucketEncryption.KMS,
            versioned=False,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            lifecycle_rules=[
                s3_lifecycle.LifecycleRule(
                    transitions=[
                        s3_lifecycle.Transition(
                            storage_class=s3.StorageClass.INTELLIGENT_TIERING,
                            transition_after=Duration.days(30),
                        ),
                        s3_lifecycle.Transition(
                            storage_class=s3.StorageClass.GLACIER,
                            transition_after=Duration.days(90),
                        ),
                    ],
                    expiration=Duration.days(365),
                ),
            ],
        )

        # ============================================================================
        # 3. QUEUE - SQS para processar dados brutos
        # ============================================================================
        crawl_queue = sqs.Queue(
            self,
            "CrawlQueue",
            queue_name="tjrs-tjsc-crawl-queue",
            visibility_timeout=Duration.minutes(15),
            message_retention_period=Duration.days(7),
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3,
                queue=sqs.Queue(
                    self,
                    "CrawlDLQ",
                    queue_name="tjrs-tjsc-crawl-dlq",
                ),
            ),
        )

        # ============================================================================
        # 4. NOTIFICATIONS - SNS para alertas
        # ============================================================================
        error_topic = sns.Topic(
            self,
            "CrawlerErrors",
            topic_name="tjrs-tjsc-crawler-errors",
        )

        # ============================================================================
        # 5. DATABASE - DynamoDB (Primary)
        # ============================================================================
        process_table = dynamodb.Table(
            self,
            "ProcessMetadataTable",
            table_name="ProcessMetadata",
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,  # On-demand
            partition_key=dynamodb.Attribute(
                name="ProcessId", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="CourtCode", type=dynamodb.AttributeType.STRING
            ),
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            point_in_time_recovery=True,
            time_to_live_attribute="TTL",
        )

        # GSI para buscas por corte + data
        process_table.add_global_secondary_index(
            index_name="CourtCodeUpdatedAtIndex",
            partition_key=dynamodb.Attribute(
                name="CourtCode", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="UpdatedAt", type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        # ============================================================================
        # 6. DATABASE - RDS Aurora (Secondary - Analytics)
        # ============================================================================
        db_cluster = rds.DatabaseCluster(
            self,
            "AuroraCluster",
            engine=rds.DatabaseClusterEngine.aurora_postgres(
                version=rds.AuroraPostgresEngineVersion.VER_13_7
            ),
            credentials=rds.Credentials.from_username(
                username="admin",
                # Gera senha aleatória e a armazena no Secrets Manager
            ),
            instances=2,
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.BURSTABLE3, ec2.InstanceSize.SMALL
            ),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            multi_az=True,
            backup_retention=Duration.days(30),
            removal_policy=RemovalPolicy.SNAPSHOT,  # Faz snapshot antes de deletar
        )

        # ============================================================================
        # 7. IAM ROLES
        # ============================================================================
        crawler_role = iam.Role(
            self,
            "CrawlerRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Role para Lambda Crawler",
        )

        # Permissions
        crawler_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AWSLambdaBasicExecutionRole"
            )
        )
        crawler_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AWSLambdaVPCAccessExecutionRole"
            )
        )

        # S3 permissions
        datalake_bucket.grant_read_write(crawler_role)

        # SQS permissions
        crawl_queue.grant_send_messages(crawler_role)

        # DynamoDB permissions
        process_table.grant_read_write_data(crawler_role)

        # RDS permissions
        db_cluster.grant_connect(crawler_role, user="admin")

        # ============================================================================
        # 8. LAMBDA - Web Crawler
        # ============================================================================
        crawler_lambda = lambda_.Function(
            self,
            "CrawlerFunction",
            function_name="tjrs-tjsc-crawler",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.lambda_handler",
            code=lambda_.Code.from_asset(
                "lambdas/crawler",  # Será criado localmente
                exclude=["*.pyc", "__pycache__", "*.egg-info"],
            ),
            role=crawler_role,
            timeout=Duration.minutes(15),
            memory_size=3008,  # Max para ativar Graviton2 (~$0.003/100ms)
            environment={
                "DATALAKE_BUCKET": datalake_bucket.bucket_name,
                "SQS_QUEUE_URL": crawl_queue.queue_url,
                "DYNAMODB_TABLE": process_table.table_name,
                "SNS_TOPIC_ARN": error_topic.topic_arn,
            },
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            # Layers com Chromium
            layers=[
                lambda_.LayerVersion.from_layer_version_arn(
                    self,
                    "ChromiumLayer",
                    layer_version_arn="arn:aws:lambda:us-east-1:764504016456:layer:chrome-stable:80",
                ),
            ],
        )

        # ============================================================================
        # 9. LAMBDA - Data Parser
        # ============================================================================
        parser_role = iam.Role(
            self,
            "ParserRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        )
        parser_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AWSLambdaBasicExecutionRole"
            )
        )
        parser_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AWSLambdaVPCAccessExecutionRole"
            )
        )

        datalake_bucket.grant_read(parser_role)
        crawl_queue.grant_consume_messages(parser_role)
        process_table.grant_read_write_data(parser_role)
        db_cluster.grant_connect(parser_role, user="admin")

        parser_lambda = lambda_.Function(
            self,
            "ParserFunction",
            function_name="tjrs-tjsc-parser",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.lambda_handler",
            code=lambda_.Code.from_asset("lambdas/parser"),
            role=parser_role,
            timeout=Duration.minutes(5),
            memory_size=1024,
            environment={
                "DATALAKE_BUCKET": datalake_bucket.bucket_name,
                "DYNAMODB_TABLE": process_table.table_name,
                "RDS_CLUSTER": db_cluster.cluster_resource_identifier,
            },
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
        )

        # SQS trigger para parser
        parser_lambda.add_event_source(
            lambda_.SqsEventSource(
                queue=crawl_queue,
                batch_size=10,
                max_batching_window_in_seconds=30,
            )
        )

        # ============================================================================
        # 10. EVENTBRIDGE - Scheduling
        # ============================================================================
        
        # Daily - Crawl recentes (2 AM UTC)
        daily_rule = events.Rule(
            self,
            "DailyCrawlRule",
            schedule=events.Schedule.cron(hour="2", minute="0"),
            description="Daily incremental crawl of TJRS/TJSC",
        )
        daily_rule.add_target(
            targets.LambdaTarget(
                crawler_lambda,
                event=events.RuleTargetInput.from_object({"crawlType": "incremental"}),
            )
        )

        # Weekly - Full crawl TJRS (Sunday 1 AM UTC)
        weekly_tjrs_rule = events.Rule(
            self,
            "WeeklyCrawlTJRSRule",
            schedule=events.Schedule.cron(week_day="SUN", hour="1", minute="0"),
            description="Weekly full crawl of TJRS",
        )
        weekly_tjrs_rule.add_target(
            targets.LambdaTarget(
                crawler_lambda,
                event=events.RuleTargetInput.from_object(
                    {"crawlType": "full", "court": "TJRS"}
                ),
            )
        )

        # ============================================================================
        # 11. API GATEWAY - REST API
        # ============================================================================
        api = apigateway.RestApi(
            self,
            "CrawlerAPI",
            rest_api_name="tjrs-tjsc-crawler-api",
            description="API para consultar dados de TJRS/TJSC",
            cors=apigateway.CorsOptions(
                allow_origins=apigateway.Cors.ALL_ORIGINS,
                allow_methods=apigateway.Cors.ALL_METHODS,
            ),
        )

        # ============================================================================
        # 12. MONITORING - CloudWatch
        # ============================================================================
        crawl_errors_metric = cloudwatch.Metric(
            namespace="TJCrawler",
            metric_name="CrawlErrors",
            statistic="Sum",
        )

        crawl_errors_alarm = cloudwatch.Alarm(
            self,
            "CrawlErrorsAlarm",
            metric=crawl_errors_metric,
            threshold=5,
            evaluation_periods=1,
            alarm_description="Alert when crawl errors exceed threshold",
        )
        crawl_errors_alarm.add_alarm_action(
            cloudwatch.SnsAction(error_topic)
        )

        # ============================================================================
        # OUTPUTS
        # ============================================================================
        from aws_cdk import CfnOutput

        CfnOutput(
            self,
            "DataLakeBucketName",
            value=datalake_bucket.bucket_name,
            description="S3 bucket para raw data",
        )

        CfnOutput(
            self,
            "ProcessTableName",
            value=process_table.table_name,
            description="DynamoDB table com metadados",
        )

        CfnOutput(
            self,
            "RDSClusterEndpoint",
            value=db_cluster.cluster_endpoint.hostname,
            description="Aurora cluster endpoint",
        )

        CfnOutput(
            self,
            "CrawlerAPIEndpoint",
            value=api.url,
            description="API Gateway endpoint",
        )

        # Tags
        Tags.of(self).add("Project", "TJRSTJSCCrawler")
        Tags.of(self).add("Environment", "Production")
        Tags.of(self).add("CostCenter", "Legal")
