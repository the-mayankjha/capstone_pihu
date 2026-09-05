import pytest
import numpy as np
from python.vad.silero import SileroVad


def test_vad_initialization_and_chunk():
    vad = SileroVad(model_path="models/wakeUp/silero_vad.onnx", threshold=0.5)
    vad.initialize()

    # Create dummy silence chunk (1280 samples of int16 zeros)
    silence = np.zeros(1280, dtype=np.int16)
    prob = vad.process_chunk(silence)
    assert 0.0 <= prob <= 1.0
    assert prob < 0.3  # Silence should have low probability

    # Test update_state
    vad.start_interaction()
    started, ended, timed_out = vad.update_state(silence)
    assert not started
    assert not ended
