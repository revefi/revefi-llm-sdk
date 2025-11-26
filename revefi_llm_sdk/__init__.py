"""Revefi LLM SDK - Traceloop-based LLM observability with llm-ingestor-service."""

import os

from opentelemetry.exporter.otlp.proto.http.trace_exporter import \
    OTLPSpanExporter
from traceloop.sdk import Traceloop
from traceloop.sdk.instruments import Instruments

# Set HTTP protocol BEFORE using Traceloop (sends protobuf over HTTP)
os.environ["OTEL_EXPORTER_OTLP_PROTOCOL"] = "http"


def init_llm_observability(
    api_key: str,
    agent_name: str,
    ingestor_url: str = None
) -> bool:
    """Initialize Traceloop OpenLLMetry with llm-ingestor-service.

    Args:
        api_key: API key for ingestor authentication
        agent_name: Name of the agent to associate with traces
        ingestor_url: URL of the llm-ingestor-service (optional, defaults to localhost:6556)

    Returns:
        Boolean indicating if initialization was successful
    """
    try:
        # Default to localhost if not specified, or use environment variable
        if ingestor_url is None:
            ingestor_url = os.getenv("LLM_INGESTOR_URL", "http://localhost:6556")

        # Disable Traceloop cloud service completely
        os.environ["TRACELOOP_BASE_URL"] = ""
        os.environ["TRACELOOP_API_KEY"] = "disabled"

        # Create custom OTLP exporter for llm-ingestor-service
        custom_exporter = OTLPSpanExporter(
            endpoint=f"{ingestor_url}/v1/traces",
            headers={"authorization": f"Bearer {api_key}"},
        )

        # Initialize Traceloop - allow only LLM instruments
        # Using custom exporter to send traces to llm-ingestor-service
        Traceloop.init(
            app_name=agent_name,
            disable_batch=False,
            exporter=custom_exporter,  # Use our custom exporter
            instruments={Instruments.OPENAI, Instruments.ANTHROPIC}  # Only LLM instruments
        )

        print(f"Traceloop OpenLLMetry initialized with llm-ingestor-service: {ingestor_url}")
        return True

    except Exception as e:
        print(f"Traceloop initialization failed: {e}")
        return False


def set_context(user_id: str, **tags) -> None:
    """Set context for LLM observability traces.
    Args:
        user_id: User's id to associate with traces
        tags: Dictionary of custom tags to associate with traces
    """
    if tags and not validate_tags(tags):
        raise ValueError("Invalid tags provided for LLM observability traces.")
    Traceloop.set_association_properties({"user_id": user_id, **tags})


# Should be a private method in the SDK
def validate_tags(tags: dict) -> bool:
    """
    Validate custom tags for LLM observability traces.

    Args:
        tags: Dictionary of custom tags to validate
    Returns:
        Boolean indicating if tags are valid
    """
    if not isinstance(tags, dict):
        return False
    if len(tags) > 50:
        return False
    for key, value in tags.items():
        if not isinstance(value, (str, int, float, bool)):
            return False
        if not isinstance(key, str) or len(key) == 0 or len(key) > 64:
            return False
        if not isinstance(value, str) or len(value) == 0 or len(value) > 128:
            return False
    return True
