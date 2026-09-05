"""
Text-to-Speech (TTS) abstraction supporting low-latency local speech synthesis.
"""

import sys
import shutil
import asyncio
import logging
import subprocess
from abc import ABC, abstractmethod
from typing import Optional, Callable, Dict, Any

logger = logging.getLogger("PIHU.TTS")


class TextToSpeech(ABC):
    """Abstract base class for Text-to-Speech engines."""

    @abstractmethod
    def speak_sync(self, text: str, on_start: Optional[Callable[[], None]] = None, on_done: Optional[Callable[[], None]] = None):
        pass

    @abstractmethod
    async def speak(self, text: str, on_start: Optional[Callable[[], None]] = None, on_done: Optional[Callable[[], None]] = None):
        pass

    @abstractmethod
    def stop(self):
        pass


class NativeMacTTS(TextToSpeech):
    """Zero-latency macOS native `say` command wrapper."""

    def __init__(self, voice: str = "Samantha", rate: int = 185):
        self.voice = voice
        self.rate = rate
        self._process: Optional[subprocess.Popen] = None

    def speak_sync(self, text: str, on_start: Optional[Callable[[], None]] = None, on_done: Optional[Callable[[], None]] = None):
        if not text.strip():
            if on_done:
                on_done()
            return

        logger.info(f"Speaking: '{text}' (voice={self.voice})")
        if on_start:
            on_start()

        try:
            cmd = ["say", "-r", str(self.rate)]
            if self.voice:
                cmd.extend(["-v", self.voice])
            cmd.append(text)

            self._process = subprocess.Popen(cmd)
            self._process.wait()
        except Exception as e:
            logger.error(f"TTS execution error: {e}")
        finally:
            self._process = None
            if on_done:
                on_done()

    async def speak(self, text: str, on_start: Optional[Callable[[], None]] = None, on_done: Optional[Callable[[], None]] = None):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.speak_sync, text, on_start, on_done)

    def stop(self):
        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
            except Exception:
                pass
            self._process = None


class MockTTS(TextToSpeech):
    """Mock TTS for unit testing."""

    def __init__(self):
        pass

    def speak_sync(self, text: str, on_start: Optional[Callable[[], None]] = None, on_done: Optional[Callable[[], None]] = None):
        logger.info(f"Mock TTS speaking: '{text}'")
        if on_start:
            on_start()
        if on_done:
            on_done()

    async def speak(self, text: str, on_start: Optional[Callable[[], None]] = None, on_done: Optional[Callable[[], None]] = None):
        self.speak_sync(text, on_start, on_done)

    def stop(self):
        pass


def create_tts_engine(cfg: Dict[str, Any]) -> TextToSpeech:
    backend = cfg.get("backend", "native").lower()
    if backend == "native" and sys.platform == "darwin" and shutil.which("say"):
        return NativeMacTTS(
            voice=cfg.get("voice", "Samantha"),
            rate=cfg.get("rate", 185),
        )
    elif backend == "mock":
        return MockTTS()
    else:
        # Fallback to NativeMacTTS if on macOS, else MockTTS
        if sys.platform == "darwin":
            return NativeMacTTS()
        return MockTTS()
