import { listen } from "@tauri-apps/api/event";
import { invoke } from "@tauri-apps/api/core";
import { PihuOrb, OrbState } from "./orb";
import { DebugController } from "./debug";

window.addEventListener("DOMContentLoaded", async () => {
  const canvas = document.getElementById("orb-canvas") as HTMLCanvasElement;
  const statusPill = document.getElementById("status-pill") as HTMLElement;

  const pihuLabel  = document.getElementById("pihu-label")  as HTMLElement;

  const orb = new PihuOrb(canvas);
  const debug = new DebugController(orb);

  // Helper to update UI state
  function updateUIState(state: OrbState) {
    orb.setState(state);

    statusPill.textContent = state;
    if (state === "IDLE") {
      statusPill.classList.remove("visible");
      pihuLabel.classList.remove("visible");
    } else {
      statusPill.classList.add("visible");
      pihuLabel.classList.add("visible");
    }

    // Update active state button in dev panel
    document.querySelectorAll(".state-btn").forEach((btn) => {
      const btnState = btn.getAttribute("data-state");
      if (btnState === state) {
        btn.classList.add("active");
      } else {
        btn.classList.remove("active");
      }
    });
  }

  // Fetch initial state
  try {
    const initialState = await invoke<OrbState>("get_state");
    updateUIState(initialState);
  } catch (e) {
    console.warn("Could not fetch initial state:", e);
  }

  // Listen for authoritative state changes from Rust
  await listen<{ state: OrbState; previous_state: OrbState; timestamp: number }>(
    "state_changed",
    (event) => {
      const { state, previous_state } = event.payload;
      debug.log("STATE", `${previous_state} → ${state}`);
      updateUIState(state);
    }
  );

  // Listen for real-time audio amplitude levels from microphone
  await listen<{ level: number }>("audio_level", (event) => {
    orb.setAudioLevel(event.payload.level);
  });

  // Listen for specific subsystem events for diagnostics
  await listen<{ wake_word: string; confidence: number }>("wake_detected", (event) => {
    debug.log("WAKE", `Detected "${event.payload.wake_word}" (conf: ${event.payload.confidence.toFixed(2)})`);
  });

  await listen<{ text: string }>("transcription_completed", (event) => {
    debug.log("STT", `"${event.payload.text}"`);
  });

  await listen<{ intent: string; confidence: number; parameters: any }>("intent_detected", (event) => {
    debug.log("INTENT", `${event.payload.intent} (params: ${JSON.stringify(event.payload.parameters)})`);
  });

  await listen<{ tool: string; arguments: any }>("tool_started", (event) => {
    debug.log("MCP", `Tool started: ${event.payload.tool}`);
  });

  await listen<{ tool: string; message: string; success: boolean }>("tool_completed", (event) => {
    debug.log("MCP", `Tool result: ${event.payload.message}`);
  });

  await listen<{ text: string }>("tts_started", (event) => {
    debug.log("TTS", `Speaking: "${event.payload.text}"`);
  });

  await listen<{ subsystem?: string; message: string }>("error", (event) => {
    debug.log("ERROR", `[${event.payload.subsystem || "SYS"}] ${event.payload.message}`);
  });

  debug.log("RUNTIME", "PIHU UI connected to Rust Core Runtime.");
});
