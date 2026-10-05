"""Unit tests for `VoiceSynth` using an in-memory fake backend.

No Piper model is downloaded and no audio is rendered — `FakeBackend` writes a
fixed byte payload so we only exercise the cache logic and error paths.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from dcs_mission_creator.core.tts.backend import VoiceBackend
from dcs_mission_creator.core.tts.piper import (
    DEFAULT_LENGTH_SCALE,
    DEFAULT_VOICE,
    PiperBackend,
)
from dcs_mission_creator.core.tts.synth import VoiceSynth


@dataclass
class FakeBackend:
    fp: str = "fake|v1"
    calls: list[tuple[str, Path]] = field(default_factory=list)
    payload: bytes = b"RIFFfakeWAV"

    def fingerprint(self) -> str:
        return self.fp

    def render_to_file(self, text: str, out_path: Path) -> None:
        self.calls.append((text, out_path))
        out_path.write_bytes(self.payload)


@dataclass
class EmptyBackend:
    def fingerprint(self) -> str:
        return "empty"

    def render_to_file(self, text: str, out_path: Path) -> None:
        # Touch the file but write nothing — simulates a misconfigured engine.
        out_path.write_bytes(b"")


def test_fake_backend_satisfies_protocol():
    assert isinstance(FakeBackend(), VoiceBackend)


def test_piper_defaults_to_slower_joe_medium():
    assert DEFAULT_VOICE == "en_US-joe-medium"
    assert DEFAULT_LENGTH_SCALE == 1.20
    assert PiperBackend().voice == "en_US-joe-medium"
    assert PiperBackend().length_scale == 1.20


def test_default_voice_synth_reads_piper_environment(monkeypatch):
    monkeypatch.setenv("PIPER_VOICE", "en_GB-alan-medium")
    monkeypatch.setenv("PIPER_LENGTH_SCALE", "1.35")

    synth = VoiceSynth()

    assert isinstance(synth.backend, PiperBackend)
    assert synth.backend.voice == "en_GB-alan-medium"
    assert synth.backend.length_scale == 1.35


@pytest.mark.parametrize("value", ["quickly", "0", "-1", "nan", "inf"])
def test_piper_rejects_invalid_environment_rate(monkeypatch, value: str):
    monkeypatch.setenv("PIPER_LENGTH_SCALE", value)

    with pytest.raises(ValueError, match="PIPER_LENGTH_SCALE"):
        PiperBackend.from_environment()


def test_render_cache_miss_calls_backend_once(tmp_path: Path):
    be = FakeBackend()
    synth = VoiceSynth(backend=be, cache_dir=tmp_path)
    wav = synth.render("hello world")
    assert wav.exists()
    assert wav.read_bytes() == be.payload
    assert len(be.calls) == 1


def test_render_cache_hit_skips_backend(tmp_path: Path):
    be = FakeBackend()
    synth = VoiceSynth(backend=be, cache_dir=tmp_path)
    synth.render("same text")
    wav2 = synth.render("same text")
    assert wav2.exists()
    assert len(be.calls) == 1  # second call hit the cache


def test_render_different_text_different_file(tmp_path: Path):
    be = FakeBackend()
    synth = VoiceSynth(backend=be, cache_dir=tmp_path)
    a = synth.render("alpha")
    b = synth.render("bravo")
    assert a != b
    assert len(be.calls) == 2


def test_render_fingerprint_changes_invalidate_cache(tmp_path: Path):
    """Two backends with different fingerprints → distinct cache files."""
    be1 = FakeBackend(fp="piper|en_US-danny-low|def|def|def")
    be2 = FakeBackend(fp="piper|en_GB-alan-medium|def|def|def")
    s1 = VoiceSynth(backend=be1, cache_dir=tmp_path)
    s2 = VoiceSynth(backend=be2, cache_dir=tmp_path)
    a = s1.render("hello")
    b = s2.render("hello")
    assert a != b


def test_render_empty_output_raises(tmp_path: Path):
    synth = VoiceSynth(backend=EmptyBackend(), cache_dir=tmp_path)
    with pytest.raises(RuntimeError, match="produced no audio"):
        synth.render("nope")


def test_cache_path_deterministic_for_same_inputs(tmp_path: Path):
    be = FakeBackend()
    synth = VoiceSynth(backend=be, cache_dir=tmp_path)
    p1 = synth._cache_path("hello")
    p2 = synth._cache_path("hello")
    assert p1 == p2
    assert p1.parent == tmp_path.resolve()
