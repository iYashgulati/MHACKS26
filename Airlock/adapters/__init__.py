from Airlock.adapters.base import AdapterError, ProviderAdapter
from Airlock.adapters.claude import ClaudeAdapter
from Airlock.adapters.codex import CodexAdapter
from Airlock.adapters.gemini import GeminiAdapter


ADAPTERS: dict[str, type[ProviderAdapter]] = {
    "claude": ClaudeAdapter,
    "codex": CodexAdapter,
    "gemini": GeminiAdapter,
}


def get_adapter(provider: str) -> ProviderAdapter:
    try:
        return ADAPTERS[provider.lower()]()
    except KeyError as error:
        raise AdapterError(f"unsupported provider: {provider}") from error


__all__ = ["AdapterError", "ClaudeAdapter", "CodexAdapter", "GeminiAdapter", "get_adapter"]
