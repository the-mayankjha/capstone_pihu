"""
Audio capture module using sounddevice for non-blocking 16kHz mono PCM streaming.
"""

import queue
import logging
import numpy as np
from typing import Optional, Callable

logger = logging.getLogger("PIHU.AUDIO")


class AudioCapture:
    """Captures continuous 16kHz mono audio and computes RMS audio levels."""

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        chunk_size: int = 1280,  # 80ms chunks
        device_index: int = -1,
        on_audio_level: Optional[Callable[[float], None]] = None,
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.device_index = None if device_index < 0 else device_index
        self.on_audio_level = on_audio_level

        self._audio_queue: queue.Queue = queue.Queue(maxsize=100)
        self._stream = None
        self._is_running = False

    def _audio_callback(self, indata, frames, time_info, status):
        """Audio stream callback running in audio thread."""
        if status:
            logger.warning(f"Audio stream status: {status}")

        # indata is float32 [-1.0, 1.0] or int16
        # Convert float32 to int16 PCM for openwakeword / silero
        if indata.dtype == np.float32:
            pcm16 = (indata[:, 0] * 32767).astype(np.int16)
        else:
            pcm16 = indata[:, 0].astype(np.int16)

        # Compute normalized RMS audio level for audio reactivity (0.0 to 1.0)
        if self.on_audio_level is not None:
            rms = np.sqrt(np.mean(pcm16.astype(np.float32) ** 2)) / 32768.0
            # Scale non-linearly to make normal speech visible in the Orb
            level = min(1.0, float(rms * 8.0))
            self.on_audio_level(level)

        try:
            self._audio_queue.put_nowait(pcm16)
        except queue.Full:
            # Drop oldest frame to avoid latency buildup
            try:
                self._audio_queue.get_nowait()
                self._audio_queue.put_nowait(pcm16)
            except queue.Empty:
                pass

    def start(self):
        """Start microphone audio stream."""
        if self._is_running:
            return

        import sounddevice as sd

        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="int16",
                blocksize=self.chunk_size,
                device=self.device_index,
                callback=self._audio_callback,
            )
            self._stream.start()
            self._is_running = True
            logger.info(f"Microphone initialized (sample_rate={self.sample_rate}, chunk_size={self.chunk_size})")
        except Exception as e:
            logger.error(f"Failed to start microphone stream (will operate in dev/virtual mode): {e}")
            self._stream = None
            self._is_running = True

    def get_chunk(self, timeout: float = 0.1) -> Optional[np.ndarray]:
        """Fetch next audio chunk (int16 numpy array)."""
        try:
            return self._audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def stop(self):
        """Stop and close microphone audio stream."""
        self._is_running = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                logger.error(f"Error closing audio stream: {e}")
            self._stream = None
        logger.info("Microphone stream stopped.")
