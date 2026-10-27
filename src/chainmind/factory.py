"""Composition root for local and AWS-backed integration implementations."""

import secrets

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from chainmind.core.config import Settings, get_settings
from chainmind.core.errors import IntegrationError
from chainmind.core.events import RunStore, SQLiteEventStore
from chainmind.core.master_data import SQLiteMasterDataStore
from chainmind.integrations.aws.event_store import DynamoDBEventStore
from chainmind.integrations.llm.base import LLMClient
from chainmind.integrations.llm.bedrock import BedrockLLMClient
from chainmind.integrations.llm.bedrock_agents import BedrockAgentsClient
from chainmind.integrations.llm.mock import MockLLMClient
from chainmind.integrations.sap.base import ApprovalWorkflowClient, AribaClient, SAPClient
from chainmind.integrations.sap.mock_ariba import MockAribaClient
from chainmind.integrations.sap.mock_s4hana import MockSAPS4HANAClient
from chainmind.integrations.sap.real_clients import (
    InMemoryApprovalWorkflowClient,
    RealAribaClient,
    RealS4HANAClient,
    SandboxWorkflowClient,
    make_transport,
)
from chainmind.notifications.channels import (
    ConsoleNotifier,
    EmailNotifier,
    SlackNotifier,
    TeamsNotifier,
)
from chainmind.notifications.links import NotificationLinkSigner
from chainmind.notifications.service import NotificationService
from chainmind.workflow.pipeline import DisruptionPipeline


def create_llm_client(settings: Settings | None = None) -> LLMClient:
    """Build the configured local or Bedrock model adapter."""

    config = settings or get_settings()
    backend = config.resolved_llm_backend
    if backend == "mock":
        return MockLLMClient()
    if backend == "bedrock_agents":
        if not config.bedrock_agent_id or not config.bedrock_agent_alias_id:
            raise IntegrationError(
                "Bedrock Agent ID and alias ID must be configured for bedrock_agents."
            )
        return BedrockAgentsClient(
            config.bedrock_agent_id,
            config.bedrock_agent_alias_id,
            config.aws_region,
        )
    return BedrockLLMClient(config.bedrock_model_id, config.aws_region)


def create_sap_clients(
    settings: Settings | None = None,
    master_data_store: SQLiteMasterDataStore | None = None,
) -> tuple[SAPClient, AribaClient, ApprovalWorkflowClient]:
    """Build the configured mock, sandbox, or Integration Suite SAP adapters."""

    config = settings or get_settings()
    backend = config.resolved_sap_backend
    if backend == "mock":
        return (
            MockSAPS4HANAClient(master_data_store),
            MockAribaClient(master_data_store),
            InMemoryApprovalWorkflowClient(),
        )
    if backend == "sandbox":
        base_url = config.sap_workflow_base_url.rstrip("/")
        transport = make_transport(
            config.model_copy(
                update={
                    "sap_integration_suite_url": base_url,
                    "sap_token_url": f"{base_url}/oauth/token",
                    "sap_client_id": config.sap_client_id or "chainmind-local",
                    "sap_client_secret": config.sap_client_secret or "chainmind-local",
                    "mode": "mock",
                }
            )
        )
        return (
            RealS4HANAClient(transport),
            RealAribaClient(transport),
            SandboxWorkflowClient(
                base_url,
                timeout_seconds=config.sap_timeout_seconds,
            ),
        )
    transport = make_transport(config)
    return (
        RealS4HANAClient(transport),
        RealAribaClient(transport),
        SandboxWorkflowClient(
            config.sap_workflow_base_url,
            timeout_seconds=config.sap_timeout_seconds,
        ),
    )


def create_notification_service(settings: Settings | None = None) -> NotificationService | None:
    """Build configured notification channels and a short-lived-link signer."""

    config = settings or get_settings()
    if not config.notification_backends:
        return None
    secret = config.notification_link_secret
    if not secret and config.mode == "aws" and config.notification_link_secret_id:
        try:
            secret_response = boto3.client(
                "secretsmanager",
                region_name=config.aws_region,
            ).get_secret_value(SecretId=config.notification_link_secret_id)
            secret = secret_response.get("SecretString")
            if not isinstance(secret, str) or len(secret) < 32:
                raise ValueError("The notification link secret is missing or too short.")
        except (BotoCoreError, ClientError, ValueError) as exc:
            raise IntegrationError(
                "The notification link signing secret could not be loaded."
            ) from exc
    if not secret:
        if config.mode == "aws":
            raise IntegrationError("A notification link signing secret is required in AWS mode.")
        secret = secrets.token_urlsafe(32)
    notifiers = []
    for backend in config.notification_backends:
        if backend == "console":
            notifiers.append(ConsoleNotifier())
        elif backend == "teams":
            if not config.notification_teams_webhook_url:
                raise IntegrationError("The Teams webhook URL is required for Teams notifications.")
            notifiers.append(TeamsNotifier(config.notification_teams_webhook_url))
        elif backend == "slack":
            if not config.notification_slack_webhook_url:
                raise IntegrationError("The Slack webhook URL is required for Slack notifications.")
            notifiers.append(SlackNotifier(config.notification_slack_webhook_url))
        elif backend == "email":
            if not config.notification_email_sender or not config.notification_email_recipient:
                raise IntegrationError(
                    "Email sender and recipient are required for email notifications."
                )
            notifiers.append(
                EmailNotifier(
                    mode=config.mode,
                    sender=config.notification_email_sender,
                    recipient=config.notification_email_recipient,
                    region_name=config.aws_region,
                    outbox_path=config.notification_email_outbox_path,
                )
            )
    signer = NotificationLinkSigner(secret, config.notification_link_ttl_minutes)
    return NotificationService(
        notifiers,
        signer,
        api_base_url=config.notification_api_base_url,
        dashboard_url=config.notification_dashboard_url,
    )


def create_pipeline(
    settings: Settings | None = None,
    store: RunStore | None = None,
    *,
    sap_client: SAPClient | None = None,
    ariba_client: AribaClient | None = None,
    llm_client: LLMClient | None = None,
    notification_service: NotificationService | None = None,
    master_data_store: SQLiteMasterDataStore | None = None,
) -> DisruptionPipeline:
    """Build a pipeline using independently configured SAP and model adapters."""

    config = settings or get_settings()
    master_data = master_data_store
    if master_data is None and config.mode == "mock" and config.resolved_sap_backend == "mock":
        master_data = SQLiteMasterDataStore(config.event_database_path)
    sap, ariba, workflow = create_sap_clients(config, master_data)
    llm = create_llm_client(config)
    return DisruptionPipeline(
        sap=sap_client or sap,
        ariba=ariba_client or ariba,
        llm=llm_client or llm,
        settings=config,
        workflow_client=workflow,
        notification_service=notification_service or create_notification_service(config),
        store=store
        or (
            DynamoDBEventStore(config.event_table_name, config.aws_region)
            if config.mode == "aws"
            else SQLiteEventStore(config.event_database_path)
        ),
    )
