"""
Silero VAD v5 wrapper using ONNX Runtime for real-time speech boundary detection.
Automatically buffers input audio into 512-sample windows (32ms at 16kHz).
"""

import os
import time
import logging
import numpy as np
import onnxruntime as ort
from typing import Optional, Tuple

logger = logging.getLogger("PIHU.VAD")


class SileroVad:
    """Silero VAD engine for speech detection and boundary calculation."""

    def __init__(
        self,
        model_path: str = "models/wakeUp/silero_vad.onnx",
        threshold: float = 0.5,
        silence_timeout_ms: int = 1200,
        min_speech_duration_ms: int = 250,
        max_command_duration_ms: int = 8000,
        sample_rate: int = 16000,
    ):
        self.model_path = model_path
        self.threshold = threshold
        self.silence_timeout_ms = silence_timeout_ms
        self.min_speech_duration_ms = min_speech_duration_ms
        self.max_command_duration_ms = max_command_duration_ms
        self.sample_rate = sample_rate

        self._session: Optional[ort.InferenceSession] = None
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._buffer = np.array([], dtype=np.float32)

        # Boundary tracking state
        self._is_speaking = False
        self._speech_start_time: Optional[float] = None
        self._last_speech_time: Optional[float] = None
        self._session_start_time: Optional[float] = None

    def initialize(self):
        """Load Silero VAD ONNX model."""
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"Silero VAD model not found at '{self.model_path}'")

        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        opts.log_severity_level = 3  # Error only

        self._session = ort.InferenceSession(self.model_path, sess_options=opts, providers=["CPUExecutionProvider"])
        self.reset()
        logger.info(f"Silero VAD loaded successfully from '{self.model_path}' (threshold={self.threshold})")

    def reset(self):
        """Reset internal recurrent states, buffer, and boundary timers."""
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._buffer = np.array([], dtype=np.float32)
        self._is_speaking = False
        self._speech_start_time = None
        self._last_speech_time = None
        self._session_start_time = None

    def start_interaction(self):
        """Mark the beginning of an interaction window (e.g. after wake detection)."""
        self.reset()
        self._session_start_time = time.time()

    def process_chunk(self, audio_chunk: np.ndarray) -> float:
        """
        Run ONNX model on audio chunk. Buffers and processes in 512-sample chunks.
        Returns maximum speech probability across the sub-chunks.
        """
        if self._session is None:
            raise RuntimeError("SileroVad must be initialized before processing audio.")

        if audio_chunk.dtype == np.int16:
            audio_float = audio_chunk.astype(np.float32) / 32768.0
        else:
            audio_float = audio_chunk.astype(np.float32)

        if audio_float.ndim > 1:
            audio_float = audio_float.flatten()

        # Append to buffer
        self._buffer = np.concatenate([self._buffer, audio_float])

        max_prob = 0.0
        window_size = 512  # 32ms at 16kHz

        while len(self._buffer) >= window_size:
            window = self._buffer[:window_size]
            self._buffer = self._buffer[window_size:]

            feed = {
                "input": np.expand_dims(window, axis=0),
                "state": self._state,
                "sr": np.array(self.sample_rate, dtype=np.int64),
            }

            out = self._session.run(None, feed)
            prob = float(out[0][0][0]) if out[0].ndim > 1 else float(out[0][0])
            if len(out) > 1:
                self._state = out[1]

            if prob > max_prob:
                max_prob = prob

        return max_prob

    def update_state(self, audio_chunk: np.ndarray) -> Tuple[bool, bool, bool]:
        """
        Process chunk and return (speech_started_now, speech_ended_now, timed_out).
        """
        now = time.time()
        prob = self.process_chunk(audio_chunk)
        is_speech = prob >= self.threshold

        speech_started_now = False
        speech_ended_now = False
        timed_out = False

        if self._session_start_time is None:
            self._session_start_time = now

        # Timeout if no speech ever started within silence_timeout
        if not self._is_speaking and self._speech_start_time is None:
            if (now - self._session_start_time) * 1000.0 >= self.silence_timeout_ms:
                timed_out = True
                return speech_started_now, speech_ended_now, timed_out

        if is_speech:
            self._last_speech_time = now
            if not self._is_speaking:
                if self._speech_start_time is None:
                    self._speech_start_time = now
                # Check minimum speech duration before committing to speaking state
                if (now - self._speech_start_time) * 1000.0 >= self.min_speech_duration_ms:
                    self._is_speaking = True
                    speech_started_now = True
        else:
            if self._is_speaking and self._last_speech_time is not None:
                # Check silence duration since last speech
                silence_dur = (now - self._last_speech_time) * 1000.0
                if silence_dur >= self.silence_timeout_ms:
                    self._is_speaking = False
                    speech_ended_now = True

        # Check maximum command duration limit
        if self._is_speaking and self._speech_start_time is not None:
            total_speech_dur = (now - self._speech_start_time) * 1000.0
            if total_speech_dur >= self.max_command_duration_ms:
                self._is_speaking = False
                speech_ended_now = True

        return speech_started_now, speech_ended_now, timed_out
