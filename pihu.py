#!/usr/bin/env python3
"""
PIHU CLI — Wakeup Detection, Benchmarking, Matrix Diagnostics & Pipeline Tool.

Usage Examples:
  python pihu.py --detect                     # Continuous wake word detection on microphone
  python pihu.py --detect --full              # Continuous wake detection + full voice interaction loop
  python pihu.py --detect --model hey_pihu --threshold 0.55  # Custom model & threshold
  python pihu.py --file speech.wav            # Test wake word detection on audio file
  python pihu.py --benchmark                  # Run latency benchmark across models
  python pihu.py --matrix                     # Run threshold sweep & noise immunity matrix
  python pihu.py --live                       # Interactive live VU meter & score visualizer
"""

import os
import sys
import time
import wave
import argparse
import datetime
import numpy as np
from typing import Dict, List, Optional, Any

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from python.vad.silero import SileroVad
from python.wakeword.engine import WakeWordEngine
from python.audio.capture import AudioCapture
from python.stt.recognizer import create_speech_recognizer
from python.intelligence.intent import IntentEngine
from python.intelligence.planner import Planner
from python.mcp.client import MCPClient
from python.tts.engine import create_tts_engine


def get_available_models(filter_model: Optional[str] = None, threshold_override: Optional[float] = None, cooldown_override: Optional[int] = None) -> List[Dict[str, Any]]:
    """Return model configurations for wake word models with optional overrides."""
    models_dir = os.path.join(PROJECT_ROOT, "models", "wakeUp")
    base_models = [
        {
            "name": "Gen-pihu",
            "model_path": os.path.join(models_dir, "Gen-pihu.onnx"),
            "threshold": 0.50,
            "cooldown_ms": 2000,
            "type": "Generalized Wake Word ('PIHU' / 'Hey PIHU')",
        },
        {
            "name": "hey_pihu",
            "model_path": os.path.join(models_dir, "hey_pihu.onnx"),
            "threshold": 0.60,
            "cooldown_ms": 2000,
            "type": "Phrase Specific ('Hey PIHU')",
        },
        {
            "name": "hi_pihu",
            "model_path": os.path.join(models_dir, "hi_pihu.onnx"),
            "threshold": 0.60,
            "cooldown_ms": 2000,
            "type": "Phrase Specific ('Hi PIHU')",
        },
        {
            "name": "pihu",
            "model_path": os.path.join(models_dir, "pihu.onnx"),
            "threshold": 0.60,
            "cooldown_ms": 2000,
            "type": "Name Specific ('PIHU')",
        },
    ]

    selected = []
    for m in base_models:
        if filter_model and filter_model.lower() != "all" and m["name"].lower() != filter_model.lower():
            continue
        cfg = dict(m)
        if threshold_override is not None:
            cfg["threshold"] = float(threshold_override)
        if cooldown_override is not None:
            cfg["cooldown_ms"] = int(cooldown_override)
        cfg["enabled"] = True
        selected.append(cfg)

    if not selected:
        print(f"Error: Model '{filter_model}' not found. Available models: {[m['name'] for m in base_models]}")
        sys.exit(1)

    return selected


def run_wake_detection(model_name: Optional[str] = None, threshold_override: Optional[float] = None, cooldown_override: Optional[int] = None, full_interaction: bool = False):
    """Real-time microphone wake word detection mode."""
    models = get_available_models(model_name, threshold_override, cooldown_override)

    print("\n" + "=" * 75)
    print(" PIHU REAL-TIME WAKE WORD DETECTOR")
    print(f" Active Models: {[m['name'] for m in models]}")
    for m in models:
        print(f"   • {m['name']:<10} | Threshold: {m['threshold']:.2f} | Cooldown: {m['cooldown_ms']}ms | {m['type']}")
    print(f" Full Voice Interaction: {'ENABLED' if full_interaction else 'DISABLED (Detection Only)'}")
    print(" Press Ctrl+C to stop listening.")
    print("=" * 75 + "\n")

    engine = WakeWordEngine(models)
    engine.initialize()

    vad_path = os.path.join(PROJECT_ROOT, "models", "wakeUp", "silero_vad.onnx")
    vad = SileroVad(model_path=vad_path)
    vad.initialize()

    tts = create_tts_engine({"backend": "native", "voice": "Samantha"}) if full_interaction else None
    stt = create_speech_recognizer({"backend": "faster-whisper", "model": "tiny.en"}) if full_interaction else None
    if stt:
        stt.initialize()

    intent_engine = IntentEngine() if full_interaction else None
    mcp_client = MCPClient() if full_interaction else None
    planner = Planner(mcp_client) if full_interaction else None

    audio = AudioCapture(sample_rate=16000, chunk_size=1280)
    audio.start()

    detection_count = 0
    state = "IDLE"  # "IDLE" | "LISTENING_COMMAND"
    command_chunks = []

    print("[PIHU][LISTENING] Microphone active. Speak 'Hey PIHU', 'Hi PIHU', or 'PIHU'...\n")

    try:
        while True:
            chunk = audio.get_chunk(timeout=0.1)
            if chunk is None:
                continue

            if state == "IDLE":
                detection = engine.process_chunk(chunk)
                if detection:
                    wake_name, conf = detection
                    detection_count += 1
                    timestamp_str = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
                    print(f"\n✨ [WAKE DETECTED #{detection_count}] at {timestamp_str}")
                    print(f"   Model: {wake_name} | Confidence: {conf:.3f} | Threshold: {engine.models[wake_name].threshold:.2f}")

                    if full_interaction:
                        print("   → [PIHU] Listening for command...")
                        state = "LISTENING_COMMAND"
                        command_chunks = []
                        vad.start_interaction()
                        if tts:
                            # Quick audible confirmation
                            tts.speak_sync("Yes?")

            elif state == "LISTENING_COMMAND":
                command_chunks.append(chunk)
                speech_started, speech_ended, timed_out = vad.update_state(chunk)

                if speech_ended:
                    print("   → [PIHU] Speech ended. Transcribing...")
                    full_audio = np.concatenate(command_chunks)
                    command_chunks = []
                    state = "IDLE"

                    transcript = stt.transcribe(full_audio)
                    print(f"   → [STT] Transcript: \"{transcript}\"")

                    if transcript.strip():
                        intent_res = intent_engine.classify(transcript)
                        print(f"   → [INTENT] Classified: {intent_res.intent} (params: {intent_res.parameters})")

                        plan = planner.plan(intent_res)
                        spoken_reply = ""
                        if plan.plan_type == "tool_execution" and plan.tool_name:
                            print(f"   → [MCP] Executing tool '{plan.tool_name}'...")
                            res = mcp_client.execute_tool(plan.tool_name, plan.arguments)
                            spoken_reply = res.message
                            print(f"   → [MCP] Tool result: {res.message}")
                        else:
                            spoken_reply = plan.direct_speech or "I am here."

                        print(f"   → [TTS] Speaking: \"{spoken_reply}\"")
                        if tts:
                            tts.speak_sync(spoken_reply)

                    print("\n[PIHU][LISTENING] Returning to IDLE. Listening for wake words...\n")

                elif timed_out:
                    print("   → [PIHU] Interaction timed out (silence). Returning to IDLE.\n")
                    state = "IDLE"
                    command_chunks = []

    except KeyboardInterrupt:
        print(f"\n\nStopped wake detector. Total wake detections: {detection_count}")
    finally:
        audio.stop()
        if stt:
            stt.shutdown()


def run_file_detection(audio_file_path: str, model_name: Optional[str] = None, threshold_override: Optional[float] = None, save_plot: bool = True):
    """Evaluate wake word detection against a recorded WAV file and plot scores."""
    if not os.path.exists(audio_file_path):
        print(f"Error: Audio file not found at '{audio_file_path}'")
        sys.exit(1)

    print("\n" + "=" * 75)
    print(f" PIHU OFFLINE AUDIO FILE WAKE DETECTION: {os.path.basename(audio_file_path)}")
    print("=" * 75)

    # Read WAV file
    with wave.open(audio_file_path, "rb") as wf:
        sr = wf.getframerate()
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        n_frames = wf.getnframes()
        raw_bytes = wf.readframes(n_frames)

    duration_sec = n_frames / sr
    print(f"Audio Format: {sr} Hz, {n_channels} channel(s), {sampwidth * 8}-bit, Duration: {duration_sec:.2f}s")

    # Convert to int16 mono
    if sampwidth == 2:
        audio_data = np.frombuffer(raw_bytes, dtype=np.int16)
    else:
        audio_data = (np.frombuffer(raw_bytes, dtype=np.float32) * 32767).astype(np.int16)

    if n_channels > 1:
        audio_data = audio_data[::n_channels]

    # Resample to 16kHz if needed
    if sr != 16000:
        print(f"Resampling from {sr}Hz to 16000Hz...")
        indices = np.round(np.arange(0, len(audio_data), sr / 16000)).astype(int)
        indices = indices[indices < len(audio_data)]
        audio_data = audio_data[indices]

    models = get_available_models(model_name, threshold_override)
    engine = WakeWordEngine(models)
    engine.initialize()

    chunk_size = 1280  # 80ms chunks
    num_chunks = len(audio_data) // chunk_size

    timeline_timestamps = []
    model_score_series = {m["name"]: [] for m in models}
    detections = []

    for i in range(num_chunks):
        chunk = audio_data[i * chunk_size : (i + 1) * chunk_size]
        time_sec = (i * chunk_size) / 16000.0
        timeline_timestamps.append(time_sec)

        pred = engine._oww_model.predict(chunk)
        for k, score in pred.items():
            m_name = engine._model_key_mapping.get(k, k)
            if m_name in model_score_series:
                model_score_series[m_name].append(float(score))
                cfg = engine.models[m_name]
                if score >= cfg.threshold:
                    detections.append({
                        "time_sec": time_sec,
                        "model": m_name,
                        "confidence": float(score),
                        "threshold": cfg.threshold,
                    })

    print(f"\nProcessing completed ({num_chunks} chunks evaluated).")
    print("-" * 75)
    print(f"Total Detections Found: {len(detections)}")
    for d in detections:
        time_fmt = f"{int(d['time_sec'] // 60):02d}:{d['time_sec'] % 60:05.2f}"
        print(f" • [{time_fmt}] Model: {d['model']:<10} | Confidence: {d['confidence']:.3f} (Threshold: {d['threshold']:.2f})")
    print("=" * 75)

    if save_plot:
        plot_file_detection(audio_file_path, timeline_timestamps, model_score_series, engine.models)


def plot_file_detection(audio_path: str, timestamps: List[float], series: Dict[str, List[float]], models_cfg: Dict[str, Any]):
    """Plot wake word prediction scores over audio timeline."""
    try:
        import matplotlib.pyplot as plt

        base_name = os.path.splitext(os.path.basename(audio_path))[0]
        out_path = os.path.join(PROJECT_ROOT, "reports", f"detection_{base_name}.png")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)

        plt.style.use("dark_background")
        fig, ax = plt.subplots(figsize=(13, 5))

        colors = ["#38bdf8", "#818cf8", "#a78bfa", "#f43f5e"]
        for idx, (m_name, scores) in enumerate(series.items()):
            color = colors[idx % len(colors)]
            ax.plot(timestamps, scores, label=f"{m_name} (Score)", color=color, linewidth=1.8, alpha=0.9)
            thresh = models_cfg[m_name].threshold
            ax.axhline(y=thresh, color=color, linestyle=":", alpha=0.5, label=f"{m_name} Threshold ({thresh:.2f})")

        ax.set_title(f"Wake Word Detection Timeline — {os.path.basename(audio_path)}", fontsize=13, fontweight="bold")
        ax.set_xlabel("Time (seconds)", fontsize=11)
        ax.set_ylabel("Confidence Score", fontsize=11)
        ax.set_ylim(-0.05, 1.05)
        ax.grid(True, linestyle="--", alpha=0.3)
        ax.legend(loc="upper right", fontsize=9)

        plt.tight_layout()
        plt.savefig(out_path, dpi=180)
        plt.close()
        print(f"\n[GRAPH SAVED]: Audio detection plot written to '{out_path}'")
    except Exception as e:
        print(f"Could not generate file detection plot: {e}")


def run_benchmark(iterations: int = 300, save_plot: bool = True) -> Dict[str, Any]:
    """Benchmark inference latency for each wake-word model and Silero VAD."""
    print("=" * 70)
    print(" PIHU WAKEUP MODELS BENCHMARK & LATENCY ANALYSIS")
    print(f" Iterations per model: {iterations} chunks (80ms audio per chunk)")
    print("=" * 70)

    results = {}
    sample_chunk = np.random.randint(-1000, 1000, size=1280, dtype=np.int16)
    vad_chunk = np.zeros(512, dtype=np.int16)

    # 1. Silero VAD
    vad_path = os.path.join(PROJECT_ROOT, "models", "wakeUp", "silero_vad.onnx")
    vad = SileroVad(model_path=vad_path)
    vad.initialize()

    for _ in range(20):
        vad.process_chunk(vad_chunk)

    vad_latencies = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        vad.process_chunk(vad_chunk)
        t1 = time.perf_counter()
        vad_latencies.append((t1 - t0) * 1000.0)

    results["Silero_VAD"] = {
        "mean_ms": np.mean(vad_latencies),
        "std_ms": np.std(vad_latencies),
        "p50_ms": np.percentile(vad_latencies, 50),
        "p95_ms": np.percentile(vad_latencies, 95),
        "p99_ms": np.percentile(vad_latencies, 99),
        "min_ms": np.min(vad_latencies),
        "max_ms": np.max(vad_latencies),
    }

    # 2. OpenWakeWord Models
    model_configs = get_available_models()
    for mcfg in model_configs:
        name = mcfg["name"]
        engine = WakeWordEngine([{"name": name, "model_path": mcfg["model_path"], "threshold": mcfg["threshold"], "cooldown_ms": 0, "enabled": True}])
        engine.initialize()

        for _ in range(20):
            engine.process_chunk(sample_chunk)

        latencies = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            engine.process_chunk(sample_chunk)
            t1 = time.perf_counter()
            latencies.append((t1 - t0) * 1000.0)

        results[name] = {
            "mean_ms": np.mean(latencies),
            "std_ms": np.std(latencies),
            "p50_ms": np.percentile(latencies, 50),
            "p95_ms": np.percentile(latencies, 95),
            "p99_ms": np.percentile(latencies, 99),
            "min_ms": np.min(latencies),
            "max_ms": np.max(latencies),
        }

    # 3. Multi-Model Combined
    all_engine = WakeWordEngine([{"name": m["name"], "model_path": m["model_path"], "threshold": m["threshold"], "cooldown_ms": 0, "enabled": True} for m in model_configs])
    all_engine.initialize()

    for _ in range(20):
        all_engine.process_chunk(sample_chunk)

    all_latencies = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        all_engine.process_chunk(sample_chunk)
        t1 = time.perf_counter()
        all_latencies.append((t1 - t0) * 1000.0)

    results["All_4_Models_Combined"] = {
        "mean_ms": np.mean(all_latencies),
        "std_ms": np.std(all_latencies),
        "p50_ms": np.percentile(all_latencies, 50),
        "p95_ms": np.percentile(all_latencies, 95),
        "p99_ms": np.percentile(all_latencies, 99),
        "min_ms": np.min(all_latencies),
        "max_ms": np.max(all_latencies),
    }

    print("\n" + "=" * 80)
    print(f"{'MODEL / ENGINE':<24} | {'AVG (ms)':<9} | {'P50 (ms)':<9} | {'P95 (ms)':<9} | {'P99 (ms)':<9} | {'MAX (ms)':<9}")
    print("-" * 80)
    for name, m in results.items():
        print(f"{name:<24} | {m['mean_ms']:<9.3f} | {m['p50_ms']:<9.3f} | {m['p95_ms']:<9.3f} | {m['p99_ms']:<9.3f} | {m['max_ms']:<9.3f}")
    print("=" * 80)

    print("\n--- LATENCY COMPARISON (Mean ms per chunk) ---")
    max_len = max(m["mean_ms"] for m in results.values())
    for name, m in results.items():
        bar_len = int((m["mean_ms"] / max_len) * 35)
        bar = "█" * bar_len
        print(f"{name:<24} | {bar:<35} {m['mean_ms']:.2f} ms")
    print("-" * 80)

    if save_plot:
        plot_benchmark_results(results)

    return results


def run_threshold_sweep(save_plot: bool = True):
    """Evaluate score matrix across noise, tones, and various thresholds."""
    print("\n" + "=" * 70)
    print(" PIHU THRESHOLD SENSITIVITY & NOISE IMMUNITY MATRIX")
    print("=" * 70)

    models = get_available_models()
    engine = WakeWordEngine([{"name": m["name"], "model_path": m["model_path"], "threshold": 0.0, "cooldown_ms": 0, "enabled": True} for m in models])
    engine.initialize()

    conditions = {
        "Digital Silence": np.zeros(1280, dtype=np.int16),
        "Low White Noise": (np.random.normal(0, 100, 1280)).astype(np.int16),
        "High White Noise": (np.random.normal(0, 1500, 1280)).astype(np.int16),
        "Speech-Band Tone (1kHz)": (np.sin(2 * np.pi * 1000 * np.arange(1280) / 16000) * 5000).astype(np.int16),
        "Low Frequency Hum (120Hz)": (np.sin(2 * np.pi * 120 * np.arange(1280) / 16000) * 8000).astype(np.int16),
    }

    matrix_scores = {m["name"]: {} for m in models}

    for cond_name, chunk in conditions.items():
        for _ in range(10):
            engine.reset()
            for _ in range(8):
                engine.process_chunk(chunk)
            pred = engine._oww_model.predict(chunk)
            for k, score in pred.items():
                m_name = engine._model_key_mapping.get(k, k)
                if m_name in matrix_scores:
                    matrix_scores[m_name][cond_name] = max(matrix_scores[m_name].get(cond_name, 0.0), float(score))

    print(f"\n{'MODEL':<14} | " + " | ".join([f"{c[:14]:<14}" for c in conditions.keys()]))
    print("-" * 90)
    for m_name, scores in matrix_scores.items():
        row = f"{m_name:<14} | "
        for cond_name in conditions.keys():
            sc = scores.get(cond_name, 0.0)
            row += f"{sc:<14.4f} | "
        print(row)
    print("=" * 90)

    print("\n--- CONFIGURED THRESHOLDS & SAFETY MARGINS ---")
    for m in models:
        max_noise = max(matrix_scores[m["name"]].values()) if matrix_scores[m["name"]] else 0.0
        cfg_val = m["threshold"]
        margin = cfg_val - max_noise
        status = "OPTIMAL" if margin > 0.3 else "SENSITIVE" if margin > 0.1 else "RISK_OF_FALSE_TRIGGER"
        print(f" • {m['name']:<10} | Configured: {cfg_val:.2f} | Max Noise: {max_noise:.4f} | Margin: {margin:+.4f} ({status})")

    if save_plot:
        plot_matrix_results(matrix_scores)


def plot_benchmark_results(results: Dict[str, Any], output_path: str = None):
    if output_path is None:
        output_path = os.path.join(PROJECT_ROOT, "reports", "wakeword_benchmark.png")
    try:
        import matplotlib.pyplot as plt

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        names = list(results.keys())
        means = [results[n]["mean_ms"] for n in names]
        p95s = [results[n]["p95_ms"] for n in names]

        plt.style.use("dark_background")
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

        colors = ["#38bdf8", "#818cf8", "#a78bfa", "#c084fc", "#f43f5e", "#fbbf24"]
        bars = ax1.barh(names, means, color=colors[: len(names)], edgecolor="white", alpha=0.85)
        ax1.set_xlabel("Latency (ms per 80ms chunk)", fontsize=11)
        ax1.set_title("PIHU Wake-Word & VAD Average Inference Latency", fontsize=12, fontweight="bold")
        ax1.grid(axis="x", linestyle="--", alpha=0.3)

        for bar in bars:
            w = bar.get_width()
            ax1.text(w + 0.05, bar.get_y() + bar.get_height() / 2, f"{w:.2f} ms", va="center", fontsize=9, color="white")

        x = np.arange(len(names))
        width = 0.35
        ax2.bar(x - width / 2, means, width, label="Mean Latency", color="#38bdf8", alpha=0.8)
        ax2.bar(x + width / 2, p95s, width, label="P95 Latency", color="#fbbf24", alpha=0.8)
        ax2.set_xticks(x)
        ax2.set_xticklabels(names, rotation=30, ha="right", fontsize=9)
        ax2.set_ylabel("Time (ms)", fontsize=11)
        ax2.set_title("Mean vs 95th Percentile Latency", fontsize=12, fontweight="bold")
        ax2.legend()
        ax2.grid(axis="y", linestyle="--", alpha=0.3)

        plt.tight_layout()
        plt.savefig(output_path, dpi=180)
        plt.close()
        print(f"\n[GRAPH SAVED]: Performance chart written to '{output_path}'")
    except Exception as e:
        print(f"Could not generate plot (matplotlib): {e}")


def plot_matrix_results(matrix_scores: Dict[str, Dict[str, float]], output_path: str = None):
    if output_path is None:
        output_path = os.path.join(PROJECT_ROOT, "reports", "wakeword_matrix.png")
    try:
        import matplotlib.pyplot as plt

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        models = list(matrix_scores.keys())
        conditions = list(next(iter(matrix_scores.values())).keys())

        data = np.zeros((len(models), len(conditions)))
        for i, m in enumerate(models):
            for j, c in enumerate(conditions):
                data[i, j] = matrix_scores[m].get(c, 0.0)

        plt.style.use("dark_background")
        fig, ax = plt.subplots(figsize=(10, 5))

        cax = ax.imshow(data, cmap="magma", vmin=0.0, vmax=1.0)
        fig.colorbar(cax, label="Prediction Score")

        ax.set_xticks(np.arange(len(conditions)))
        ax.set_yticks(np.arange(len(models)))
        ax.set_xticklabels(conditions, rotation=25, ha="right", fontsize=10)
        ax.set_yticklabels(models, fontsize=10, fontweight="bold")
        ax.set_title("PIHU Wake-Word Noise Immunity & Score Matrix", fontsize=13, fontweight="bold", pad=15)

        for i in range(len(models)):
            for j in range(len(conditions)):
                val = data[i, j]
                text_color = "black" if val > 0.6 else "white"
                ax.text(j, i, f"{val:.4f}", ha="center", va="center", color=text_color, fontsize=10)

        plt.tight_layout()
        plt.savefig(output_path, dpi=180)
        plt.close()
        print(f"[GRAPH SAVED]: Sensitivity matrix plot written to '{output_path}'")
    except Exception as e:
        print(f"Could not generate matrix plot: {e}")


def run_live_monitor(model_name: Optional[str] = None):
    """Live interactive console showing real-time audio energy and model score bars."""
    print("=" * 75)
    print(" PIHU LIVE AUDIO & WAKE-WORD MONITOR")
    print(" Speak 'Hey PIHU', 'Hi PIHU', or 'PIHU' to observe live score bars.")
    print(" Press Ctrl+C to stop.")
    print("=" * 75)

    models = get_available_models(model_name)
    engine = WakeWordEngine([{"name": m["name"], "model_path": m["model_path"], "threshold": 0.0, "cooldown_ms": 0, "enabled": True} for m in models])
    engine.initialize()

    vad_path = os.path.join(PROJECT_ROOT, "models", "wakeUp", "silero_vad.onnx")
    vad = SileroVad(model_path=vad_path)
    vad.initialize()

    audio = AudioCapture(sample_rate=16000, chunk_size=1280)
    audio.start()

    try:
        while True:
            chunk = audio.get_chunk(timeout=0.1)
            if chunk is None:
                continue

            rms = np.sqrt(np.mean(chunk.astype(np.float32) ** 2)) / 32768.0
            vu_bar = "█" * int(min(1.0, rms * 10) * 12)

            vad_prob = vad.process_chunk(chunk)
            vad_indicator = "[SPEECH]" if vad_prob >= 0.5 else "[SILENCE]"

            prediction = engine._oww_model.predict(chunk)

            scores_str = []
            for k, score in prediction.items():
                m_name = engine._model_key_mapping.get(k, k)
                bar = "█" * int(score * 10)
                scores_str.append(f"{m_name}: {score:.2f} |{bar:<10}|")

            status_line = f"\rVU: |{vu_bar:<12}| {vad_indicator} | " + "  ".join(scores_str)
            sys.stdout.write(status_line)
            sys.stdout.flush()

    except KeyboardInterrupt:
        print("\n\nLive monitor stopped.")
    finally:
        audio.stop()


def main():
    banner = """
  ╔════════════════════════════════════════════════════════════════════════════╗
  ║                              PIHU AI RUNTIME                               ║
  ║         Desktop AI Interaction Layer — Wakeup & Diagnostics CLI            ║
  ╚════════════════════════════════════════════════════════════════════════════╝
"""
    parser = argparse.ArgumentParser(
        description=banner,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
COMMAND MODES:
  --detect, -d          Start continuous real-time microphone wake word detector.
  --detect --full, -f   Start wake detector + execute full voice command pipeline upon detection.
  --file, -i <WAV>      Evaluate wake word detection on a WAV file & plot timeline score graph.
  --live, -l            Start interactive live VU energy meter & real-time model score bars.
  --benchmark, -b       Benchmark inference latency percentiles (min, avg, p50, p95, p99, max).
  --matrix, -m          Evaluate sensitivity & noise immunity matrix across acoustic conditions.

TUNING & FILTERS:
  --model <NAME>        Target specific model: 'Gen-pihu', 'hey_pihu', 'hi_pihu', 'pihu', or 'all'.
  --threshold, -t <VAL> Override confidence threshold (e.g. 0.55).
  --cooldown, -c <MS>   Override debounce cooldown duration in milliseconds (e.g. 2000).
  --iterations, -n <N>  Number of iterations for benchmark (default: 300).
  --no-plot             Disable generating and saving visual PNG graphs to reports/.

EXAMPLES:
  # 1. Listen for wake words on microphone:
  python pihu.py --detect

  # 2. Listen for wake words and run full voice interaction:
  python pihu.py --detect --full

  # 3. Test only 'hey_pihu' model with custom 0.55 threshold:
  python pihu.py --detect --model hey_pihu --threshold 0.55

  # 4. Analyze recorded WAV file and generate timeline chart:
  python pihu.py --file speech_sample.wav

  # 5. Run live interactive console visualizer:
  python pihu.py --live

  # 6. Run latency benchmark & generate performance charts:
  python pihu.py --benchmark -n 500
""",
    )

    # Operational Modes
    parser.add_argument("--detect", "-d", "--wake", action="store_true", help="Start microphone wake word detector")
    parser.add_argument("--full", "-f", action="store_true", help="Enable full voice interaction loop on wake detection")
    parser.add_argument("--file", "-i", type=str, metavar="WAV_FILE", help="Evaluate wake word detection on an audio WAV file")
    parser.add_argument("--benchmark", "-b", action="store_true", help="Run latency & throughput benchmark")
    parser.add_argument("--matrix", "-m", action="store_true", help="Run threshold sweep and noise immunity matrix")
    parser.add_argument("--live", "-l", action="store_true", help="Start interactive live audio visualizer")

    # Options & Modifiers
    parser.add_argument("--model", type=str, default=None, help="Filter by model: Gen-pihu, hey_pihu, hi_pihu, pihu, or all")
    parser.add_argument("--threshold", "-t", type=float, default=None, help="Override detection threshold (e.g. 0.55)")
    parser.add_argument("--cooldown", "-c", type=int, default=None, help="Override debounce cooldown in ms (e.g. 2000)")
    parser.add_argument("--iterations", "-n", type=int, default=300, help="Number of iterations for benchmark")
    parser.add_argument("--no-plot", action="store_true", help="Disable generating and saving PNG graphs")

    args = parser.parse_args()
    save_plot = not args.no_plot

    if args.detect:
        run_wake_detection(
            model_name=args.model,
            threshold_override=args.threshold,
            cooldown_override=args.cooldown,
            full_interaction=args.full,
        )
    elif args.file:
        run_file_detection(
            audio_file_path=args.file,
            model_name=args.model,
            threshold_override=args.threshold,
            save_plot=save_plot,
        )
    elif args.live:
        run_live_monitor(model_name=args.model)
    elif args.benchmark:
        run_benchmark(iterations=args.iterations, save_plot=save_plot)
    elif args.matrix:
        run_threshold_sweep(save_plot=save_plot)
    else:
        # If no flag specified, display help overview and run quick status matrix
        parser.print_help()
        print("\n" + "=" * 75)
        print(" Running Quick Diagnostic Benchmark & Matrix Sweep:")
        print("=" * 75)
        run_benchmark(iterations=100, save_plot=save_plot)
        run_threshold_sweep(save_plot=save_plot)


if __name__ == "__main__":
    main()
