"""Composition root for local and AWS-backed integration implementations."""

from chainmind.core.config import Settings, get_settings
from chainmind.core.events import EventStore, RunStore
from chainmind.integrations.aws.event_store import DynamoDBEventStore
from chainmind.integrations.llm.base import LLMClient
from chainmind.integrations.llm.bedrock import BedrockLLMClient
from chainmind.integrations.llm.mock import MockLLMClient
from chainmind.integrations.sap.base import AribaClient, SAPClient
from chainmind.integrations.sap.mock_ariba import MockAribaClient
from chainmind.integrations.sap.mock_s4hana import MockSAPS4HANAClient
from chainmind.integrations.sap.real_stubs import RealAribaClient, RealSAPClient
from chainmind.workflow.pipeline import DisruptionPipeline


def create_llm_client(settings: Settings | None = None) -> LLMClient:
    """Build the configured mock or Bedrock model adapter."""

    config = settings or get_settings()
    if config.mode == "mock":
        return MockLLMClient()
    return BedrockLLMClient(config.bedrock_model_id, config.aws_region)


def create_sap_clients(settings: Settings | None = None) -> tuple[SAPClient, AribaClient]:
    """Build the configured mock or Integration Suite SAP adapter placeholders."""

    config = settings or get_settings()
    if config.mode == "mock":
        return MockSAPS4HANAClient(), MockAribaClient()
    return RealSAPClient(), RealAribaClient()


def create_pipeline(
    settings: Settings | None = None,
    store: RunStore | None = None,
    *,
    sap_client: SAPClient | None = None,
    ariba_client: AribaClient | None = None,
    llm_client: LLMClient | None = None,
) -> DisruptionPipeline:
    """Build a pipeline using offline mocks or AWS-mode adapters."""

    config = settings or get_settings()
    sap, ariba = create_sap_clients(config)
    llm = create_llm_client(config)
    return DisruptionPipeline(
        sap=sap_client or sap,
        ariba=ariba_client or ariba,
        llm=llm_client or llm,
        settings=config,
        store=store
        or (
            DynamoDBEventStore(config.event_table_name, config.aws_region)
            if config.mode == "aws"
            else EventStore()
        ),
    )
