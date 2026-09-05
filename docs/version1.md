# PIHU Prototype — Walkthrough & Documentation

The first functional prototype of **PIHU** — an AI interaction layer for the desktop — has been implemented.

---

## 1. What Was Implemented

1. **Authoritative State Machine & Rust Core Runtime** ([`src-tauri/src/runtime.rs`](file:///Users/mayankjha/Documents/projects/capstone_pihu/src-tauri/src/runtime.rs)):
   - Single source of truth for runtime states (`IDLE`, `WAKE_DETECTED`, `LISTENING`, `TRANSCRIBING`, `THINKING`, `PLANNING`, `EXECUTING`, `RESPONDING`, `ERROR`).
   - Emits real state changes to the Tauri frontend via `state_changed` event.
2. **Python Subprocess Lifecycle & Process Manager** ([`src-tauri/src/process_manager.rs`](file:///Users/mayankjha/Documents/projects/capstone_pihu/src-tauri/src/process_manager.rs)):
   - Launches long-lived Python AI runtime process.
   - Monitors exit status; isolates failures without crashing Tauri; supports controlled auto-restart and manual recovery.
3. **Bidirectional Stdio JSON-Lines IPC Protocol** ([`src-tauri/src/ipc.rs`](file:///Users/mayankjha/Documents/projects/capstone_pihu/src-tauri/src/ipc.rs) & [`python/ipc/protocol.py`](file:///Users/mayankjha/Documents/projects/capstone_pihu/python/ipc/protocol.py)):
   - Zero-overhead asynchronous streaming of structured events between Python and Rust.
4. **Persistent Microphone Pipeline** ([`python/audio/capture.py`](file:///Users/mayankjha/Documents/projects/capstone_pihu/python/audio/capture.py)):
   - Non-blocking 16kHz mono audio streaming with real-time RMS energy meter.
5. **Silero VAD v5 Engine** ([`python/vad/silero.py`](file:///Users/mayankjha/Documents/projects/capstone_pihu/python/vad/silero.py)):
   - Uses [`models/wakeUp/silero_vad.onnx`](file:///Users/mayankjha/Documents/projects/capstone_pihu/models/wakeUp/silero_vad.onnx).
   - Dynamic boundary segmentation: `speech_started`, `speech_ended`, silence timeout, and max duration cut-off.
6. **OpenWakeWord Multi-Model Engine** ([`python/wakeword/engine.py`](file:///Users/mayankjha/Documents/projects/capstone_pihu/python/wakeword/engine.py)):
   - Simultaneously runs generalized model (`Gen-pihu.onnx`) and phrase-specific models (`hey_pihu.onnx`, `hi_pihu.onnx`, `pihu.onnx`).
   - Individual configurable thresholds and debounce cooldowns.
7. **Speech Recognizer (STT)** ([`python/stt/recognizer.py`](file:///Users/mayankjha/Documents/projects/capstone_pihu/python/stt/recognizer.py)):
   - Pluggable abstraction with local, low-latency `faster-whisper` (`tiny.en`) engine.
8. **Intent Engine & Action Planner** ([`python/intelligence/intent.py`](file:///Users/mayankjha/Documents/projects/capstone_pihu/python/intelligence/intent.py) & [`python/intelligence/planner.py`](file:///Users/mayankjha/Documents/projects/capstone_pihu/python/intelligence/planner.py)):
   - Classifies utterances (`GET_TIME`, `GET_DATE`, `OPEN_URL`, `OPEN_APPLICATION`, `SEARCH_WEB`, `IDENTITY`, `GREETING`) and generates execution plans.
9. **MCP Capability Layer** ([`python/mcp/client.py`](file:///Users/mayankjha/Documents/projects/capstone_pihu/python/mcp/client.py) & [`python/mcp/tools.py`](file:///Users/mayankjha/Documents/projects/capstone_pihu/python/mcp/tools.py)):
   - Extensible tool execution layer with built-in tools (`get_time`, `get_date`, `open_url`, `open_application`, `web_search`).
10. **Low-Latency Local TTS Engine** ([`python/tts/engine.py`](file:///Users/mayankjha/Documents/projects/capstone_pihu/python/tts/engine.py)):
    - Native macOS `say` synthesis with immediate `tts_started` and `tts_completed` lifecycle hooks.
11. **Dark, Minimalist Procedural Orb UI** ([`src/orb.ts`](file:///Users/mayankjha/Documents/projects/capstone_pihu/src/orb.ts)):
    - Fully event-driven Canvas animation system (no fake timers).
    - Real audio-reactive waveforms during `LISTENING`.
12. **Dev / Diagnostics Mode** ([`src/debug.ts`](file:///Users/mayankjha/Documents/projects/capstone_pihu/src/debug.ts) & [`index.html`](file:///Users/mayankjha/Documents/projects/capstone_pihu/index.html)):
    - Collapsible debug drawer (`Cmd+D`) with state triggers, command simulator chips, and live event log stream.
13. **Centralized Configuration** ([`config/pihu.toml`](file:///Users/mayankjha/Documents/projects/capstone_pihu/config/pihu.toml)):
    - All audio, VAD, wake-word model paths, thresholds, STT/TTS settings in one place.

---

## 2. Project Structure

```
capstone_pihu/
├── config/
│   └── pihu.toml                  # Centralized configuration
├── docs/
│   └── HLA.md                     # High-level architecture documentation
├── models/
│   └── wakeUp/                    # ONNX wake models & Silero VAD
│       ├── Gen-pihu.onnx
│       ├── hey_pihu.onnx
│       ├── hey_pihu.onnx.data
│       ├── hi_pihu.onnx
│       ├── hi_pihu.onnx.data
│       ├── pihu(g).onnx.data
│       ├── pihu.onnx
│       ├── pihu.onnx.data
│       └── silero_vad.onnx
├── python/                        # Python AI Layer
│   ├── main.py                    # Process entrypoint & loop
│   ├── requirements.txt
│   ├── audio/capture.py           # 16kHz PCM audio capture & RMS energy
│   ├── vad/silero.py              # Silero VAD v5 ONNX wrapper
│   ├── wakeword/engine.py         # Multi-model wake word detector
│   ├── stt/recognizer.py          # faster-whisper STT
│   ├── intelligence/
│   │   ├── intent.py              # Intent classifier
│   │   └── planner.py             # Action planner
│   ├── mcp/
│   │   ├── client.py              # Tool manager
│   │   └── tools.py               # Built-in system/web tools
│   ├── tts/engine.py              # Low-latency speech synthesis
│   └── ipc/protocol.py            # Stdio JSON-lines protocol
├── src-tauri/                     # Rust Runtime Core
│   ├── Cargo.toml
│   ├── tauri.conf.json            # Floating transparent window config
│   ├── capabilities/default.json
│   └── src/
│       ├── lib.rs
│       ├── main.rs                # Desktop shell boot & window setup
│       ├── runtime.rs             # Authoritative state machine
│       ├── process_manager.rs     # Python process supervisor
│       ├── ipc.rs                 # Event router
│       └── commands.rs            # Tauri invoke handlers
├── src/                           # Frontend UI
│   ├── orb.ts                     # Procedural Canvas Orb
│   ├── debug.ts                   # Dev diagnostics overlay
│   ├── main.ts                    # Tauri event bindings
│   └── style.css                  # Dark, minimal styling
├── tests/                         # Unit tests
│   ├── test_vad.py
│   ├── test_wakeword.py
│   ├── test_intent.py
│   └── test_mcp.py
├── index.html
├── package.json
└── vite.config.ts
```

---

## 3. PIHU Authoritative State Machine

```
              ┌─────────┐
              │  IDLE   │ ◄─────────────────────────┐
              └────┬────┘                           │
                   │ wake_detected                  │
                   ▼                                │
           ┌───────────────┐                        │
           │ WAKE_DETECTED │                        │
           └───────┬───────┘                        │
                   │ immediate                      │
                   ▼                                │
             ┌───────────┐                          │
             │ LISTENING │ (audio-reactive)         │
             └─────┬─────┘                          │
                   │ speech_ended                   │
                   ▼                                │
            ┌──────────────┐                        │
            │ TRANSCRIBING │ (faster-whisper)       │
            └──────┬───────┘                        │
                   │ transcription_completed        │
                   ▼                                │
             ┌───────────┐                          │
             │ THINKING  │ (intent engine)          │
             └─────┬─────┘                          │
                   │ planning_started               │
                   ▼                                │
             ┌───────────┐                          │
             │ PLANNING  │ (action planner)         │
             └─────┬─────┘                          │
                   │ tool_started                   │
                   ▼                                │
             ┌───────────┐                          │
             │ EXECUTING │ (MCP tool)               │
             └─────┬─────┘                          │
                   │ tts_started                    │
                   ▼                                │
            ┌─────────────┐                         │
            │ RESPONDING  │ (native TTS)            │
            └──────┬──────┘                         │
                   │ tts_completed                  │
                   └────────────────────────────────┘
```

---

## 4. Wake-Word Model Configuration & Thresholds

Configured centrally in [`config/pihu.toml`](file:///Users/mayankjha/Documents/projects/capstone_pihu/config/pihu.toml):

| Model Name | Path | Threshold | Cooldown | Enabled |
| :--- | :--- | :--- | :--- | :--- |
| **Gen-pihu** | `models/wakeUp/Gen-pihu.onnx` | `0.50` | `2000 ms` | `true` |
| **hey_pihu** | `models/wakeUp/hey_pihu.onnx` | `0.60` | `2000 ms` | `true` |
| **hi_pihu** | `models/wakeUp/hi_pihu.onnx` | `0.60` | `2000 ms` | `true` |
| **pihu** | `models/wakeUp/pihu.onnx` | `0.60` | `2000 ms` | `true` |

> [!TIP]
> To adjust sensitivity without modifying any code, edit the `threshold` values in [`config/pihu.toml`](file:///Users/mayankjha/Documents/projects/capstone_pihu/config/pihu.toml). Lower values (e.g. `0.45`) increase sensitivity, while higher values (e.g. `0.70`) reduce false positives.

---

## 5. Verification & Test Results

### 1. Automated Python Test Suite
Ran `PYTHONPATH=. .venv/bin/pytest tests/`:
- `tests/test_intent.py`: **PASSED** (Time, Date, URL, App, Web Search, Identity)
- `tests/test_mcp.py`: **PASSED** (Tools & Planner dispatch)
- `tests/test_vad.py`: **PASSED** (Silero VAD initialization, 512-sample buffer, boundary detection)
- `tests/test_wakeword.py`: **PASSED** (All 4 models loaded and tested against audio buffer)

### 2. End-to-End IPC Integration Test
Simulated the complete runtime lifecycle:
- `ready` event received
- Command 1: `"What time is it?"` → `GET_TIME` intent → `get_time` MCP tool execution → `"It is 7:40 PM."` TTS response → state returns to `IDLE`.
- Command 2: `"Open GitHub"` → `OPEN_URL` intent → `open_url` MCP tool execution (`https://github.com`) → `"Opening github."` TTS response → state returns to `IDLE`.
- Trigger Wake Word: `"hey_pihu"` → `WAKE_DETECTED` → `LISTENING` → real-time `audio_level` streaming.

### 3. Rust & Tauri Compilation
`cargo build` in `src-tauri/` finished with 0 errors.

---

## 6. How to Run PIHU

### Prerequisites
- Python 3.10 virtual environment in `.venv/` (already created with all dependencies installed)
- Node.js & npm (installed)
- Rust toolchain (`cargo`, `rustc`) (installed)

### Running in Development Mode
To launch the Tauri application with the floating Orb overlay:
```bash
npm run tauri dev
```

### Running the Python AI Subprocess Standalone (For Audio/CLI Testing)
```bash
PYTHONPATH=. .venv/bin/python python/main.py --config config/pihu.toml
```

### Using Dev / Debug Mode in the App
- Press **`Cmd + D`** (or click the small gear icon ⚙ in the top right corner).
- Click any state button (`IDLE`, `WAKE`, `LISTENING`, `TRANSCRIBE`, `THINKING`, `PLANNING`, `EXECUTING`, `RESPONDING`, `ERROR`) to visually test the Orb.
- Click any quick command chip (e.g. *"What time is it?"*, *"Open GitHub"*) or type a command to test the complete intent-planner-MCP-TTS pipeline.
- View live event timestamps and payloads in the real-time event log.

---

## 7. Known Limitations & Recommended Next Steps

### Limitations
- The first prototype focuses on single-turn interactions with basic system/web MCP tools.
- Remote LLMs / contextual memory are intentionally stubbed in favor of zero-latency local intent patterns for the MVP.

### Recommended Next Steps
1. **System Tray Integration**: Add a menu bar tray icon in `src-tauri/src/main.rs` to allow quick toggling between background and active listening.
2. **Additional MCP Servers**: Connect external MCP servers (e.g. filesystem, calendar, browser automation).
3. **Screen Context / Vision Layer**: Feed active window and screen accessibility metadata into the Planner for contextual voice commands (e.g. *"Summarize this window"*).
