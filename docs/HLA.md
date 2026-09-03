# PIHU Prototype — Technical Architecture

PIHU will be built as a **desktop AI interaction layer** using **Tauri + Rust** for the application shell and system-level functionality, with **Python subprocesses** responsible for AI-specific workloads.

The architecture is intentionally divided into two major layers:

**Tauri/Rust → System, UI, lifecycle, communication, orchestration**

**Python → AI perception, speech, intelligence, and model execution**

---

## 1. High-Level Architecture

```text
                         ┌───────────────────────┐
                         │        PIHU           │
                         │  AI Interaction Layer │
                         └───────────┬───────────┘
                                     │
                    ┌────────────────┴────────────────┐
                    │                                 │
                    ▼                                 ▼
          ┌──────────────────┐              ┌──────────────────┐
          │   Tauri + Rust   │              │ Python AI Layer  │
          │                  │              │                  │
          │ • Desktop App    │◄────────────►│ • VAD            │
          │ • Orb UI         │   IPC/IPC     │ • Wake Word      │
          │ • System APIs    │              │ • STT            │
          │ • Process Mgmt   │              │ • Intent Engine  │
          │ • Event Routing  │              │ • Planner        │
          │ • MCP Client     │              │ • TTS            │
          └────────┬─────────┘              └──────────────────┘
                   │
                   ▼
          ┌──────────────────┐
          │ Operating System │
          │                  │
          │ Apps / Windows   │
          │ Files / Browser  │
          │ System Controls  │
          └──────────────────┘
```

---

# 2. Why Tauri + Rust + Python?

The three technologies have clearly separated responsibilities.

### Tauri

Tauri provides the desktop application layer.

It will handle:

* PIHU's desktop window
* Floating Orb
* Transparent/always-on-top UI
* System tray
* Application lifecycle
* Frontend ↔ Rust communication
* Rust ↔ Python process management

The frontend can be built with a lightweight web stack such as:

```text
HTML
CSS
TypeScript
```

or a framework if required.

---

### Rust

Rust becomes the **PIHU Runtime / System Core**.

It should be responsible for:

* Starting and stopping Python processes
* Managing subprocess lifecycle
* IPC between Python and Tauri
* Event routing
* State management
* System-level operations
* MCP communication
* Permissions
* OS integration
* Application/window management
* Maintaining PIHU's always-running runtime

Conceptually:

```text
                 PIHU RUNTIME
                      │
          ┌───────────┼───────────┐
          │           │           │
          ▼           ▼           ▼
       Orb UI      Python AI     MCP
          │           │           │
          └───────────┼───────────┘
                      │
                      ▼
                     OS
```

Rust should **not** contain the AI models themselves.

---

# 3. Python AI Subprocess Layer

Python will be used because the AI ecosystem is significantly easier to work with there.

Instead of putting everything into one Python process, PIHU can eventually have specialized workers.

```text
Python AI Runtime
│
├── audio_worker.py
│   ├── Microphone
│   ├── VAD
│   └── OpenWakeWord
│
├── speech_worker.py
│   ├── STT
│   └── Transcription
│
├── intelligence_worker.py
│   ├── Intent Engine
│   ├── Context
│   └── Planner
│
└── speech_output.py
    └── TTS
```

For the first prototype, however, these can remain inside a **single Python AI process** to reduce complexity.

---

# 4. Communication Architecture

The most important architectural decision is how Rust and Python communicate.

The initial prototype should use an **event-based IPC protocol**.

```text
Python
   │
   │ Event
   ▼
Rust Runtime
   │
   │ Event
   ▼
Tauri Frontend
   │
   ▼
Orb
```

And the reverse direction:

```text
Orb / User
     │
     ▼
Tauri
     │
     ▼
Rust Runtime
     │
     ▼
Python AI
```

A lightweight JSON message protocol can be used.

Example:

```json
{
  "event": "wake_detected"
}
```

Then:

```json
{
  "event": "state_changed",
  "state": "listening"
}
```

Then:

```json
{
  "event": "transcription_ready",
  "text": "open GitHub"
}
```

Then:

```json
{
  "event": "intent_detected",
  "intent": "open_application",
  "target": "github"
}
```

---

# 5. PIHU State Machine

Rust should maintain the **authoritative PIHU state**.

```text
                 ┌───────┐
                 │ IDLE  │
                 └───┬───┘
                     │
                Wake detected
                     │
                     ▼
             ┌───────────────┐
             │ WAKE_DETECTED │
             └───────┬───────┘
                     │
                     ▼
              ┌────────────┐
              │ LISTENING  │
              └─────┬──────┘
                    │
                    ▼
             ┌──────────────┐
             │ TRANSCRIBING │
             └──────┬───────┘
                    │
                    ▼
              ┌───────────┐
              │ THINKING  │
              └─────┬─────┘
                    │
                    ▼
              ┌───────────┐
              │ PLANNING  │
              └─────┬─────┘
                    │
                    ▼
              ┌───────────┐
              │ EXECUTING │
              └─────┬─────┘
                    │
                    ▼
             ┌────────────┐
             │ RESPONDING │
             └──────┬─────┘
                    │
                    ▼
                 ┌──────┐
                 │ IDLE │
                 └──────┘
```

The Orb doesn't independently determine these states.

It receives the state from Rust and renders the appropriate visual behavior.

---

# 6. The Orb Architecture

The Orb is a **visual representation of PIHU's internal state**.

```text
                  PIHU STATE
                      │
                      ▼
                 Rust Runtime
                      │
                      ▼
                  Tauri Event
                      │
                      ▼
                    Orb
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
     LISTENING     THINKING      EXECUTING
```

This allows the Orb to communicate PIHU's activity without exposing technical implementation details.

For example:

### Idle

```text
       ·
```

### Listening

```text
      ◉
    ╱   ╲
   ╱     ╲
```

### Thinking

```text
      ◌
   ◌  ◉  ◌
      ◌
```

### Planning

```text
       ◉
      / \
     ·   ·
      \ /
       ·
```

### Executing

```text
       ◉
       │
    ───┼───
       │
      MCP
```

The visual language should remain **premium, minimal, dark, and non-gimmicky**, rather than relying on the typical bright AI gradients.

---

# 7. Complete Interaction Flow

A complete PIHU interaction will look like this:

```text
USER
 │
 │ "Hey PIHU"
 ▼
Microphone
 │
 ▼
VAD
 │
 ▼
OpenWakeWord
 │
 │ Wake detected
 ▼
Rust Runtime
 │
 ├──────────────► Orb → WAKE_DETECTED
 │
 ▼
Python AI
 │
 ▼
LISTENING
 │
 ▼
Speech → Text
 │
 ▼
"Open GitHub"
 │
 ▼
Intent Engine
 │
 ▼
OPEN_APPLICATION
 │
 ▼
Planner
 │
 ▼
MCP
 │
 ▼
System / Browser Tool
 │
 ▼
Result
 │
 ▼
TTS
 │
 ▼
Rust Runtime
 │
 ▼
Orb → RESPONDING
 │
 ▼
"GitHub is open."
 │
 ▼
Orb → IDLE
```

---

# 8. MCP's Position in PIHU

MCP should sit **after reasoning/planning and before execution**.

```text
User
 ↓
STT
 ↓
Intent Engine
 ↓
Planner
 ↓
MCP
 ↓
Tool
 ↓
Result
 ↓
LLM
 ↓
TTS
```

This gives PIHU a clean separation:

**LLM decides what should happen.**

**MCP defines how PIHU can interact with external capabilities.**

**Rust provides the system-level runtime and security boundary.**

---

# 9. First Prototype Scope

The first working version should intentionally remain small.

### Build

* Tauri desktop application
* Rust runtime
* Floating Orb
* Microphone capture
* VAD
* OpenWakeWord
* Python subprocess
* STT
* Basic intent engine
* Basic planner
* MCP integration
* TTS
* State synchronization between Python → Rust → Orb

### Initial commands

Start with approximately 3–5 commands:

```text
"Hey PIHU, what time is it?"

"Hey PIHU, open GitHub."

"Hey PIHU, search for [something]."

"Hey PIHU, open my browser."

"Hey PIHU, tell me today's date."
```

Once this pipeline is stable, additional capabilities can be added without changing the fundamental architecture.

---

# 10. The Key Design Principle

PIHU should not be designed as:

```text
Python AI + UI
```

Instead:

```text
                 PIHU
                  │
        ┌─────────┴─────────┐
        │                   │
   SYSTEM LAYER        INTELLIGENCE
        │                   │
      Rust                Python
        │                   │
        └─────────┬─────────┘
                  │
               Orb UI
```

**Rust is the body.**

**Python is the intelligence layer.**

**The Orb is the interaction surface.**

**MCP is the capability bridge.**

This separation will allow the prototype to evolve into the larger PIHU architecture without having to rewrite the foundation.

