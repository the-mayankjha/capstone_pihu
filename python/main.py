"""
PIHU Python AI Runtime — Main Entrypoint.
Coordinates AudioCapture, Silero VAD, OpenWakeWord, STT, Intent, Planner, MCP, TTS, and Stdio IPC.
"""

import os
import sys
import time
import asyncio
import logging
import argparse
import numpy as np

# Use tomllib in Python 3.11+ or tomli in Python 3.10
if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from python.ipc.protocol import IpcProtocol
from python.audio.capture import AudioCapture
from python.vad.silero import SileroVad
from python.wakeword.engine import WakeWordEngine
from python.stt.recognizer import create_speech_recognizer
from python.intelligence.intent import IntentEngine
from python.intelligence.planner import Planner
from python.mcp.client import MCPClient
from python.tts.engine import create_tts_engine

# Configure logging to stderr so stdout is reserved for IPC
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger("PIHU.RUNTIME")


class PihuPythonRuntime:
    """Core Python AI pipeline for PIHU."""

    def __init__(self, config_path: str):
        self.config_path = config_path
        self.config = self._load_config()

        self.ipc = IpcProtocol()
        self.mcp_client = MCPClient()
        self.intent_engine = IntentEngine()
        self.planner = Planner(self.mcp_client)

        self.vad: Optional[SileroVad] = None
        self.wakeword: Optional[WakeWordEngine] = None
        self.stt = None
        self.tts = None
        self.audio_capture: Optional[AudioCapture] = None

        # Internal state tracking
        self.current_mode = "IDLE"  # "IDLE" | "LISTENING" | "PROCESSING" | "RESPONDING"
        self._command_audio_chunks = []
        self._running = False
        self._last_audio_level_emit = 0.0

    def _load_config(self) -> dict:
        if not os.path.exists(self.config_path):
            logger.warning(f"Config file not found at '{self.config_path}', using defaults.")
            return {}
        with open(self.config_path, "rb") as f:
            return tomllib.load(f)

    def initialize(self):
        """Initialize all AI models and engines."""
        logger.info("[PIHU][RUNTIME] Initializing AI models...")

        # 1. VAD
        vad_cfg = self.config.get("vad", {})
        self.vad = SileroVad(
            model_path=vad_cfg.get("model_path", "models/wakeUp/silero_vad.onnx"),
            threshold=vad_cfg.get("threshold", 0.5),
            silence_timeout_ms=vad_cfg.get("silence_timeout_ms", 1200),
            min_speech_duration_ms=vad_cfg.get("min_speech_duration_ms", 250),
            max_command_duration_ms=vad_cfg.get("max_command_duration_ms", 8000),
        )
        self.vad.initialize()

        # 2. Wake Word Engine
        ww_models_cfg = self.config.get("wakeword", {}).get("models", [])
        self.wakeword = WakeWordEngine(ww_models_cfg)
        self.wakeword.initialize()

        # 3. STT
        stt_cfg = self.config.get("stt", {})
        self.stt = create_speech_recognizer(stt_cfg)
        self.stt.initialize()

        # 4. TTS
        tts_cfg = self.config.get("tts", {})
        self.tts = create_tts_engine(tts_cfg)

        # 5. Audio Capture
        audio_cfg = self.config.get("audio", {})
        self.audio_capture = AudioCapture(
            sample_rate=audio_cfg.get("sample_rate", 16000),
            channels=audio_cfg.get("channels", 1),
            chunk_size=audio_cfg.get("chunk_size", 1280),
            device_index=audio_cfg.get("input_device_index", -1),
            on_audio_level=self._on_audio_level,
        )

        # Register IPC command handlers
        self.ipc.register_handler("simulate_command", self._handle_simulate_command)
        self.ipc.register_handler("trigger_wake", self._handle_trigger_wake)
        self.ipc.register_handler("stop", self._handle_stop)

        logger.info("[PIHU][RUNTIME] All components initialized successfully.")

    def _on_audio_level(self, level: float):
        """Callback for microphone audio amplitude."""
        # Only emit audio levels during LISTENING to minimize IPC traffic
        if self.current_mode == "LISTENING":
            now = time.time()
            if now - self._last_audio_level_emit >= 0.05:  # 20 FPS max
                self._last_audio_level_emit = now
                self.ipc.send_event("audio_level", level=level)

    async def _handle_simulate_command(self, data: dict):
        """Dev command to simulate text utterance without speech."""
        text = data.get("text", "")
        logger.info(f"Simulating command: '{text}'")
        await self._process_text_command(text)

    async def _handle_trigger_wake(self, data: dict):
        """Dev command to simulate wake word."""
        wake_name = data.get("wake_word", "hey_pihu")
        logger.info(f"Simulating wake word: '{wake_name}'")
        self._on_wake_detected(wake_name, 1.0)

    async def _handle_stop(self, data: dict):
        logger.info("Received stop request via IPC.")
        self._running = False

    def _on_wake_detected(self, wake_word: str, confidence: float):
        """Called when wake word is detected."""
        logger.info(f"[PIHU][WAKE] Detected wake word '{wake_word}' (conf={confidence:.3f})")
        self.current_mode = "LISTENING"
        self._command_audio_chunks = []
        if self.vad:
            self.vad.start_interaction()

        self.ipc.send_event(
            "wake_detected",
            wake_word=wake_word,
            confidence=confidence,
            timestamp=int(time.time() * 1000),
        )

    async def _process_text_command(self, transcript: str):
        """Process transcribed text through Intent -> Planner -> MCP -> TTS."""
        if not transcript.strip():
            logger.info("Empty transcript, returning to IDLE.")
            self.current_mode = "IDLE"
            self.ipc.send_event("idle")
            return

        self.current_mode = "PROCESSING"
        self.ipc.send_event("transcription_completed", text=transcript)

        # 1. Intent Engine
        intent_res = self.intent_engine.classify(transcript)
        self.ipc.send_event("intent_detected", **intent_res.to_dict())

        # 2. Planning
        self.ipc.send_event("planning_started")
        plan = self.planner.plan(intent_res)
        self.ipc.send_event("planning_completed", **plan.to_dict())

        spoken_text = ""

        # 3. Execution (MCP Tool vs Direct Response)
        if plan.plan_type == "tool_execution" and plan.tool_name:
            self.ipc.send_event("tool_started", tool=plan.tool_name, arguments=plan.arguments)
            tool_res = self.mcp_client.execute_tool(plan.tool_name, plan.arguments)
            self.ipc.send_event("tool_completed", tool=plan.tool_name, **tool_res.to_dict())
            spoken_text = tool_res.message or "Done."
        else:
            spoken_text = plan.direct_speech or "I am here."

        # 4. Text-to-Speech
        self.current_mode = "RESPONDING"

        def on_tts_start():
            logger.info(f"[PIHU][TTS] Speaking: '{spoken_text}'")
            self.ipc.send_event("tts_started", text=spoken_text)

        def on_tts_done():
            logger.info("[PIHU][TTS] Speech completed.")
            self.ipc.send_event("tts_completed")
            self.current_mode = "IDLE"
            self.ipc.send_event("idle")

        await self.tts.speak(spoken_text, on_start=on_tts_start, on_done=on_tts_done)

    async def run(self):
        """Main event loop."""
        self._running = True
        await self.ipc.start()

        if self.audio_capture:
            self.audio_capture.start()

        logger.info("[PIHU][RUNTIME] AI pipeline running. Ready for wake words.")
        self.ipc.send_event("ready")

        loop = asyncio.get_running_loop()

        while self._running:
            try:
                # Retrieve audio chunk from capture queue in executor to avoid blocking asyncio
                chunk = await loop.run_in_executor(None, self.audio_capture.get_chunk, 0.05)
                if chunk is None:
                    await asyncio.sleep(0.01)
                    continue

                if self.current_mode == "IDLE":
                    # Check wake word
                    detection = self.wakeword.process_chunk(chunk)
                    if detection:
                        wake_name, conf = detection
                        self._on_wake_detected(wake_name, conf)

                elif self.current_mode == "LISTENING":
                    self._command_audio_chunks.append(chunk)

                    # Update VAD state
                    speech_started, speech_ended, timed_out = self.vad.update_state(chunk)

                    if speech_started:
                        logger.info("[PIHU][VAD] Speech started.")
                        self.ipc.send_event("speech_started")

                    if speech_ended:
                        logger.info("[PIHU][VAD] Speech ended.")
                        self.ipc.send_event("speech_ended")
                        self.ipc.send_event("transcription_started")

                        # Combine audio
                        full_audio = np.concatenate(self._command_audio_chunks)
                        self._command_audio_chunks = []
                        self.current_mode = "PROCESSING"

                        # Run STT in executor
                        transcript = await loop.run_in_executor(None, self.stt.transcribe, full_audio)
                        asyncio.create_task(self._process_text_command(transcript))

                    elif timed_out:
                        logger.info("[PIHU][VAD] Silence timeout during LISTENING.")
                        self.current_mode = "IDLE"
                        self._command_audio_chunks = []
                        self.ipc.send_event("timeout")
                        self.ipc.send_event("idle")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[PIHU][RUNTIME] Error in main loop: {e}", exc_info=True)
                self.ipc.send_event("error", subsystem="RUNTIME", message=str(e))
                await asyncio.sleep(0.1)

        # Cleanup
        if self.audio_capture:
            self.audio_capture.stop()
        if self.tts:
            self.tts.stop()
        if self.stt:
            self.stt.shutdown()
        await self.ipc.stop()
        logger.info("[PIHU][RUNTIME] Python AI runtime shut down cleanly.")


def main():
    parser = argparse.ArgumentParser(description="PIHU Python AI Runtime")
    parser.add_argument("--config", default="config/pihu.toml", help="Path to pihu.toml config file")
    args = parser.parse_args()

    runtime = PihuPythonRuntime(config_path=args.config)
    try:
        runtime.initialize()
        asyncio.run(runtime.run())
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received.")
    except Exception as e:
        logger.critical(f"Fatal error in Python runtime: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
