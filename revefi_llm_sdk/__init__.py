"""Revefi LLM SDK - Traceloop-based LLM observability with llm-ingestor-service."""

import contextvars
import logging
import os
from typing import Optional, Sequence

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import \
    OTLPSpanExporter
from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from traceloop.sdk import Traceloop
from traceloop.sdk.instruments import Instruments

logger = logging.getLogger(__name__)

# Traceloop sends protobuf over HTTP; this must be set before Traceloop is used.
os.environ["OTEL_EXPORTER_OTLP_PROTOCOL"] = "http"

# Span attribute carrying a per-request test_prompt_id from the request thread to the export thread.
_TEST_PROMPT_ID_ATTR = "revefi.test_prompt_id"
# HTTP header the ingestor reads to map a run's traces to its test_prompt_id.
_TEST_PROMPT_ID_HEADER = "test-prompt-id"

# Current request's test_prompt_id; "" means production / no test.
_test_prompt_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "revefi_test_prompt_id", default=""
)


def set_request_test_prompt_id(test_prompt_id: Optional[str]) -> None:
    """Tag the current request's spans with a test_prompt_id (test-only; pass "" / None in production).
    Must be called on the same thread/context that creates the spans.
    """
    _test_prompt_id_var.set(test_prompt_id or "")


class _TestPromptIdSpanProcessor(SpanProcessor):
    """Stamps each span at start with the request's test_prompt_id so it survives to the export thread."""

    def on_start(self, span: Span, parent_context=None) -> None:
        try:
            test_prompt_id = _test_prompt_id_var.get()
            if test_prompt_id:
                span.set_attribute(_TEST_PROMPT_ID_ATTR, test_prompt_id)
        except Exception:
            # Telemetry bookkeeping must never break span creation.
            logger.exception("Failed to stamp test_prompt_id on span")

    def on_end(self, span: ReadableSpan) -> None:
        pass

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


class _TestPromptIdRoutingExporter(SpanExporter):
    """Splits each batch by test_prompt_id, sending one OTLP POST per id with its `test-prompt-id` header.
    Spans without an id (production) form a single group exported with no extra header.
    """

    def __init__(self, endpoint_url: str, base_headers: dict):
        self._endpoint_url = endpoint_url
        self._base_headers = dict(base_headers)
        self._default_exporter = OTLPSpanExporter(
            endpoint=endpoint_url, headers=dict(base_headers)
        )
        # One cached exporter per distinct test_prompt_id; stays empty in production.
        self._exporters_by_id: dict = {}

    def _exporter_for(self, test_prompt_id: Optional[str]) -> OTLPSpanExporter:
        if not test_prompt_id:
            return self._default_exporter
        exporter = self._exporters_by_id.get(test_prompt_id)
        if exporter is None:
            headers = dict(self._base_headers)
            headers[_TEST_PROMPT_ID_HEADER] = test_prompt_id
            exporter = OTLPSpanExporter(endpoint=self._endpoint_url, headers=headers)
            self._exporters_by_id[test_prompt_id] = exporter
        return exporter

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        try:
            groups: dict = {}
            for span in spans:
                attributes = span.attributes or {}
                groups.setdefault(attributes.get(_TEST_PROMPT_ID_ATTR), []).append(span)
            result = SpanExportResult.SUCCESS
            for test_prompt_id, group in groups.items():
                group_result = self._exporter_for(test_prompt_id).export(group)
                if group_result != SpanExportResult.SUCCESS:
                    result = group_result
            return result
        except Exception:
            # Never drop telemetry on a routing error; fall back to a plain export.
            logger.exception("test_prompt_id routing failed; falling back to plain export")
            return self._default_exporter.export(spans)

    def shutdown(self) -> None:
        self._default_exporter.shutdown()
        for exporter in self._exporters_by_id.values():
            exporter.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        flushed = self._default_exporter.force_flush(timeout_millis)
        for exporter in self._exporters_by_id.values():
            flushed = exporter.force_flush(timeout_millis) and flushed
        return flushed


def init_llm_observability(
    api_key: str,
    service_name: str,
    ingestor_url: str = None
) -> bool:
    """Initialize Traceloop OpenLLMetry with llm-ingestor-service.

    Args:
        api_key: API key for ingestor authentication
        service_name: Name of the service to associate with traces
        ingestor_url: URL of the llm-ingestor-service (optional, defaults to localhost:3000)

    Returns:
        Boolean indicating if initialization was successful
    """
    try:
        logger.info(f"Starting LLM observability initialization for service: {service_name}")

        # Default to localhost if not specified, or use environment variable
        if ingestor_url is None:
            ingestor_url = os.getenv("LLM_INGESTOR_URL", "http://localhost:3000")

        logger.info(f"Using ingestor URL: {ingestor_url}")
        logger.info(f"API key provided: {'Yes' if api_key else 'No'}")

        # Disable Traceloop cloud service completely
        os.environ["TRACELOOP_BASE_URL"] = ""
        os.environ["TRACELOOP_API_KEY"] = "disabled"

        # Create custom OTLP exporter for llm-ingestor-service
        endpoint_url = f"{ingestor_url}/api/v1/traces/ingest"
        logger.info(f"Creating OTLP exporter with endpoint: {endpoint_url}")

        base_headers = {"authorization": f"Bearer {api_key}"}
        # Routing exporter: reads each span's test_prompt_id (stamped per request by
        # _TestPromptIdSpanProcessor from set_request_test_prompt_id) and splits the batch into one
        # POST per id, each carrying the `test-prompt-id` header. Self-gating: with no id on any span
        # (production) it sends one POST with no extra header, identical to the plain exporter.
        custom_exporter = _TestPromptIdRoutingExporter(endpoint_url, base_headers)
        logger.info("OTLP exporter created successfully")

        # Initialize Traceloop - allow only LLM instruments
        # Using custom exporter to send traces to llm-ingestor-service
        logger.info("Initializing Traceloop with custom exporter including langchain")
        Traceloop.init(
            app_name=service_name,
            disable_batch=False,
            exporter=custom_exporter,  # Use our custom exporter
            instruments={
                Instruments.OPENAI,
                Instruments.ANTHROPIC,
                Instruments.LANGCHAIN,
                Instruments.GOOGLE_GENERATIVEAI  # Google Gemini SDK
            }  # Only LLM instruments
        )

        # Register the stamping processor AFTER Traceloop.init (it installs the SDK TracerProvider).
        # It only writes an attribute when set_request_test_prompt_id was called with a non-empty id.
        try:
            trace.get_tracer_provider().add_span_processor(_TestPromptIdSpanProcessor())
        except Exception:
            logger.exception("Failed to register test_prompt_id span processor")

        logger.info(f"Traceloop OpenLLMetry initialized successfully with llm-ingestor-service: {ingestor_url}")
        return True

    except Exception as e:
        logger.error(f"Traceloop initialization failed: {e}")
        return False


def set_context(user_id: str, agent_name: str, **tags) -> None:
    """Set context for LLM observability traces.
    Args:
        user_id: User's id to associate with traces
        agent_name: Name of the agent to associate with traces
        tags: Dictionary of custom tags to associate with traces
    """
    if tags and not validate_tags(tags):
        raise ValueError("Invalid tags provided for LLM observability traces.")
    Traceloop.set_association_properties(
        {"user_id": user_id, "agent_name": agent_name, **tags}
    )


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
