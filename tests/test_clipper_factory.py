"""Tests for rendering backend factory."""
import pytest
from src.clipper.backends.base import ClipRenderingBackend
from src.clipper.backends.factory import ClipRenderingBackendFactory
from src.clipper.exceptions import ClipRenderingError, InvalidClipRequestError
from src.clipper.models import ClipConfiguration, ClipFormat, ClipRequest, ClipCandidate, RenderedClip

class FakeBackend(ClipRenderingBackend):
    def render_clip(self, request: ClipRequest, candidate: ClipCandidate, progress_callback=None) -> RenderedClip: raise NotImplementedError
    def validate_backend(self, configuration: ClipConfiguration) -> None: pass
    def backend_name(self) -> str: return "fake"
    def supported_formats(self) -> frozenset[ClipFormat]: return frozenset({ClipFormat.MP4})

def test_factory_registers_selects_and_lists_backends() -> None:
    factory = ClipRenderingBackendFactory({"fake": FakeBackend}, "fake")
    assert factory.available_backends() == ("fake",)
    assert isinstance(factory.get_backend("fake"), FakeBackend)
    assert isinstance(factory.get_default_backend(), FakeBackend)

def test_factory_translates_invalid_and_broken_backends() -> None:
    factory = ClipRenderingBackendFactory()
    with pytest.raises(InvalidClipRequestError): factory.get_default_backend()
    with pytest.raises(InvalidClipRequestError): factory.get_backend("missing")
    factory.register_backend("broken", lambda: object())
    with pytest.raises(ClipRenderingError): factory.get_backend("broken")
    with pytest.raises(InvalidClipRequestError): ClipRenderingBackendFactory({"fake": FakeBackend}, "missing")
    factory.register_backend("crash", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(ClipRenderingError): factory.get_backend("crash")
