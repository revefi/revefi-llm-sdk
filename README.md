# Revefi LLM SDK

A minimal Python SDK for LLM observability with Revefi's monitoring platform.

## Installation

```bash
pip install revefi-llm-sdk
```

## Quick Start

```python
from revefi_llm_sdk import init_llm_observability

# Initialize the SDK
init_llm_observability(
    api_key="your-revefi-api-key",
    agent_name="my-llm-agent",
    ingestor_url="https://your-revefi-instance.com"  # optional
)

# Your LLM calls will now be automatically tracked
import openai
client = openai.OpenAI()
response = client.chat.completions.create(
    model="gpt-3.5-turbo",
    messages=[{"role": "user", "content": "Hello!"}]
)
```

## Configuration

- `api_key`: Your Revefi API key for authentication
- `agent_name`: Name identifier for your agent/application  
- `ingestor_url`: Revefi ingestor service URL (defaults to localhost:6556)

## Supported LLM Providers

- OpenAI
- Anthropic

## Environment Variables

```bash
LLM_INGESTOR_URL=https://your-revefi-instance.com
```

## License

MIT