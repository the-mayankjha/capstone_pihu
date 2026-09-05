import pytest
import numpy as np
from python.wakeword.engine import WakeWordEngine


def test_wakeword_model_loading():
    configs = [
        {
            "name": "hey_pihu",
            "model_path": "models/wakeUp/hey_pihu.onnx",
            "threshold": 0.6,
            "cooldown_ms": 2000,
            "enabled": True,
        },
        {
            "name": "hi_pihu",
            "model_path": "models/wakeUp/hi_pihu.onnx",
            "threshold": 0.6,
            "cooldown_ms": 2000,
            "enabled": True,
        },
        {
            "name": "pihu",
            "model_path": "models/wakeUp/pihu.onnx",
            "threshold": 0.6,
            "cooldown_ms": 2000,
            "enabled": True,
        },
        {
            "name": "Gen-pihu",
            "model_path": "models/wakeUp/Gen-pihu.onnx",
            "threshold": 0.5,
            "cooldown_ms": 2000,
            "enabled": True,
        },
    ]

    engine = WakeWordEngine(configs)
    engine.initialize()

    # Pass 1280 samples of silence
    chunk = np.zeros(1280, dtype=np.int16)
    detection = engine.process_chunk(chunk)
    # Silence should not trigger wake word
    assert detection is None
