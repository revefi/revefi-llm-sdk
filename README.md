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
    ingestor_url="https://your-revefi-instance.com"
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

## Development & Distribution

### Building Distribution Files

The `dist/` directory contains the distribution files that are built from the source code and uploaded to PyPI. These files are generated using Python's build tools:

```bash
# Build distribution files (generates .whl and .tar.gz files in dist/)
python -m build

# This creates:
# - dist/revefi_llm_sdk-{version}-py3-none-any.whl (wheel package)
# - dist/revefi_llm_sdk-{version}.tar.gz (source distribution)
```
Update the version in pyproject.toml before building to ensure the correct version is included in the distribution files.

### Publishing to PyPI

The distribution files are uploaded to the Python Package Index (PyPI) registry using `twine`:

```bash
# Upload to PyPI (requires valid PyPI credentials)
python -m twine upload dist/*

# For testing, upload to Test PyPI first:
python -m twine upload --repository testpypi dist/*
```

**Note**: The files in `dist/` are automatically generated and should not be manually edited. They are created from the source code defined in `revefi_llm_sdk/` and the project configuration in `pyproject.toml`.

## License

MIT
