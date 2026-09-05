"""
OpenWakeWord Engine supporting multiple models with individual thresholds and cooldowns.
"""

import os
import time
import logging
import numpy as np
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger("PIHU.WAKE")


class WakeModelConfig:
    def __init__(
        self,
        name: str,
        model_path: str,
        data_path: Optional[str] = None,
        threshold: float = 0.5,
        cooldown_ms: int = 2000,
        enabled: bool = True,
    ):
        self.name = name
        self.model_path = model_path
        self.data_path = data_path
        self.threshold = threshold
        self.cooldown_ms = cooldown_ms
        self.enabled = enabled
        self.last_detection_time: float = 0.0


class WakeWordEngine:
    """Manages multi-model wake word detection using openWakeWord with per-model thresholds."""

    def __init__(self, model_configs: List[Dict[str, Any]]):
        self.models: Dict[str, WakeModelConfig] = {}
        for cfg in model_configs:
            model = WakeModelConfig(
                name=cfg["name"],
                model_path=cfg["model_path"],
                data_path=cfg.get("data_path"),
                threshold=cfg.get("threshold", 0.5),
                cooldown_ms=cfg.get("cooldown_ms", 2000),
                enabled=cfg.get("enabled", True),
            )
            self.models[model.name] = model

        self._oww_model = None
        self._model_key_mapping: Dict[str, str] = {}  # maps openwakeword output keys to config names

    def initialize(self):
        """Load openWakeWord models."""
        enabled_models = [m for m in self.models.values() if m.enabled]
        if not enabled_models:
            logger.warning("No wake word models enabled.")
            return

        for m in enabled_models:
            if not os.path.exists(m.model_path):
                raise FileNotFoundError(f"Wake word model not found: {m.model_path}")

        import openwakeword
        from openwakeword.model import Model

        model_paths = [m.model_path for m in enabled_models]
        logger.info(f"Loading {len(model_paths)} wake word model(s): {[m.name for m in enabled_models]}")

        # Initialize openWakeWord Model instance
        self._oww_model = Model(
            wakeword_models=model_paths,
            inference_framework="onnx",
        )

        # Map openWakeWord model keys (filenames without extension or model tags) to our configured names
        oww_keys = list(self._oww_model.models.keys())
        logger.info(f"Loaded openWakeWord keys: {oww_keys}")

        for model in enabled_models:
            matched = False
            base_filename = os.path.splitext(os.path.basename(model.model_path))[0]
            for key in oww_keys:
                if key == base_filename or key.startswith(base_filename) or base_filename.startswith(key):
                    self._model_key_mapping[key] = model.name
                    matched = True
                    break
            if not matched and oww_keys:
                # Fallback to direct name match if available
                self._model_key_mapping[model.name] = model.name

        logger.info(f"Wake word engine ready. Model key mapping: {self._model_key_mapping}")

    def reset(self):
        """Reset internal prediction buffers."""
        if self._oww_model is not None:
            self._oww_model.reset()

    def process_chunk(self, audio_chunk: np.ndarray) -> Optional[Tuple[str, float]]:
        """
        Feed 16kHz 16-bit PCM audio chunk and check for wake word detection.
        Returns (wake_word_name, confidence) if triggered and above threshold, else None.
        """
        if self._oww_model is None:
            return None

        # Predict using openwakeword
        # openwakeword accepts 16-bit int PCM audio numpy array
        if audio_chunk.dtype != np.int16:
            audio_int16 = (audio_chunk * 32767).astype(np.int16)
        else:
            audio_int16 = audio_chunk

        prediction = self._oww_model.predict(audio_int16)
        now = time.time()

        for key, score in prediction.items():
            model_name = self._model_key_mapping.get(key, key)
            if model_name in self.models:
                cfg = self.models[model_name]
                if not cfg.enabled:
                    continue

                if score >= cfg.threshold:
                    # Check debounce / cooldown
                    elapsed_ms = (now - cfg.last_detection_time) * 1000.0
                    if elapsed_ms >= cfg.cooldown_ms:
                        cfg.last_detection_time = now
                        logger.info(f"Wake word detected: '{cfg.name}' (confidence={score:.3f}, threshold={cfg.threshold})")
                        self.reset()
                        return cfg.name, float(score)

        return None
