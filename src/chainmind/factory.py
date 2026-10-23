"""Composition root for local and AWS-backed integration implementations."""

from chainmind.core.config import Settings, get_settings
from chainmind.core.errors import IntegrationError
from chainmind.core.events import EventStore, RunStore
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
) -> tuple[SAPClient, AribaClient, ApprovalWorkflowClient]:
    """Build the configured mock, sandbox, or Integration Suite SAP adapters."""

    config = settings or get_settings()
    backend = config.resolved_sap_backend
    if backend == "mock":
        return MockSAPS4HANAClient(), MockAribaClient(), InMemoryApprovalWorkflowClient()
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


def create_pipeline(
    settings: Settings | None = None,
    store: RunStore | None = None,
    *,
    sap_client: SAPClient | None = None,
    ariba_client: AribaClient | None = None,
    llm_client: LLMClient | None = None,
) -> DisruptionPipeline:
    """Build a pipeline using independently configured SAP and model adapters."""

    config = settings or get_settings()
    sap, ariba, workflow = create_sap_clients(config)
    llm = create_llm_client(config)
    return DisruptionPipeline(
        sap=sap_client or sap,
        ariba=ariba_client or ariba,
        llm=llm_client or llm,
        settings=config,
        workflow_client=workflow,
        store=store
        or (
            DynamoDBEventStore(config.event_table_name, config.aws_region)
            if config.mode == "aws"
            else EventStore()
        ),
    )
