"""Language-specific post-processors for code edits."""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from fledgling.edit.region import Region


@runtime_checkable
class PostProcessor(Protocol):
    """Protocol for language-specific post-processing of edits."""

    def adjust_indentation(
        self, content: str, target_context: Optional[Region],
    ) -> str:
        """Adjust indentation of content to match the target context."""
        ...


_REGISTRY: dict[str, PostProcessor] = {}


def register_postprocessor(language: str, pp: PostProcessor) -> None:
    _REGISTRY[language] = pp


def get_postprocessor(language: str) -> Optional[PostProcessor]:
    return _REGISTRY.get(language)


# Auto-register built-in post-processors
def _init_registry():
    from fledgling.edit.postprocess.python import PythonPostProcessor
    register_postprocessor("python", PythonPostProcessor())

_init_registry()
