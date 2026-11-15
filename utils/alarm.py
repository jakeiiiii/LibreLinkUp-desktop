"""Loud looping alarm sound for glucose / no-signal alerts.

winsound.Beep is quiet and blocks the UI thread, so instead we synthesize a
full-amplitude two-tone square-wave siren into a WAV file once, then loop it
asynchronously with winsound.PlaySound until stop() is called.
"""
import logging
import math
import struct
import tempfile
import wave
from pathlib import Path

import winsound

logger = logging.getLogger(__name__)

_SAMPLE_RATE = 22050
_AMPLITUDE = 32000          # near int16 max — as loud as the output device allows
_TONES = (1000, 1600)        # alternate between these (Hz) — harsh and attention-grabbing
_TONE_SECONDS = 0.22
_CYCLES = 4                  # tone pairs per loop iteration
_PAUSE_SECONDS = 0.15        # short gap at the end of each loop

_wav_path: Path | None = None
_playing = False


def _build_wav() -> Path:
    path = Path(tempfile.gettempdir()) / "LibreLinkUp_alarm.wav"
    frames = bytearray()
    tone_len = int(_SAMPLE_RATE * _TONE_SECONDS)
    for _ in range(_CYCLES):
        for freq in _TONES:
            period = _SAMPLE_RATE / freq
            for i in range(tone_len):
                # Square wave: perceived much louder than a sine at the same peak
                s = _AMPLITUDE if (i % period) < (period / 2) else -_AMPLITUDE
                frames += struct.pack("<h", s)
    frames += b"\x00\x00" * int(_SAMPLE_RATE * _PAUSE_SECONDS)

    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(_SAMPLE_RATE)
        w.writeframes(bytes(frames))
    return path


def _ensure_wav() -> Path:
    global _wav_path
    if _wav_path is None or not _wav_path.exists():
        _wav_path = _build_wav()
    return _wav_path


def start() -> None:
    """Start looping the alarm (no-op if already playing)."""
    global _playing
    if _playing:
        return
    try:
        path = _ensure_wav()
        winsound.PlaySound(
            str(path),
            winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_LOOP,
        )
        _playing = True
    except Exception as e:
        logger.error("Failed to play alarm: %s", e)


def stop() -> None:
    """Stop the alarm if it is playing."""
    global _playing
    if not _playing:
        return
    try:
        winsound.PlaySound(None, winsound.SND_PURGE)
    except Exception:
        pass
    _playing = False


def is_playing() -> bool:
    return _playing
