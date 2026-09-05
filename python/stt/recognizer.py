"""
Speech Recognition (STT) abstraction supporting faster-whisper and fallback engines.
"""

import io
import wave
import logging
import numpy as np
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

logger = logging.getLogger("PIHU.STT")


class SpeechRecognizer(ABC):
    """Abstract base class for Speech-to-Text recognizers."""

    @abstractmethod
    def initialize(self):
        """Initialize the model."""
        pass

    @abstractmethod
    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        """
        Transcribe 1D int16 / float32 audio numpy array into text string.
        """
        pass

    @abstractmethod
    def shutdown(self):
        """Clean up resources."""
        pass


class FasterWhisperRecognizer(SpeechRecognizer):
    """Local STT using faster-whisper."""

    def __init__(self, model_size: str = "tiny.en", language: str = "en", beam_size: int = 1):
        self.model_size = model_size
        self.language = language
        self.beam_size = beam_size
        self._model = None

    def initialize(self):
        from faster_whisper import WhisperModel

        logger.info(f"Loading faster-whisper model '{self.model_size}' (language={self.language})...")
        # CPU with int8 quantization for ultra-fast low-latency local inference on mac
        try:
            self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
        except Exception:
            # Fallback to float32 if int8 is not supported
            self._model = WhisperModel(self.model_size, device="cpu", compute_type="float32")
        logger.info("faster-whisper model loaded successfully.")

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        if self._model is None:
            raise RuntimeError("FasterWhisperRecognizer must be initialized before transcribing.")

        if audio.size == 0:
            return ""

        # faster-whisper expects float32 numpy array normalized to [-1.0, 1.0]
        if audio.dtype == np.int16:
            audio_float = audio.astype(np.float32) / 32768.0
        else:
            audio_float = audio.astype(np.float32)

        segments, info = self._model.transcribe(
            audio_float,
            language=self.language,
            beam_size=self.beam_size,
            vad_filter=False,  # We already did Silero VAD segmentation
        )

        text_parts = [segment.text.strip() for segment in segments]
        transcript = " ".join(text_parts).strip()
        logger.info(f"STT Transcript: '{transcript}'")
        return transcript

    def shutdown(self):
        self._model = None


class MockSpeechRecognizer(SpeechRecognizer):
    """Mock recognizer for offline unit tests."""

    def __init__(self, fixed_response: str = "what time is it"):
        self.fixed_response = fixed_response

    def initialize(self):
        logger.info("Mock STT initialized.")

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        return self.fixed_response

    def shutdown(self):
        pass


def create_speech_recognizer(cfg: Dict[str, Any]) -> SpeechRecognizer:
    backend = cfg.get("backend", "faster-whisper").lower()
    if backend == "faster-whisper":
        return FasterWhisperRecognizer(
            model_size=cfg.get("model", "tiny.en"),
            language=cfg.get("language", "en"),
            beam_size=cfg.get("beam_size", 1),
        )
    elif backend == "mock":
        return MockSpeechRecognizer()
    else:
        logger.warning(f"Unknown STT backend '{backend}', falling back to faster-whisper.")
        return FasterWhisperRecognizer()
