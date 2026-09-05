use serde_json::Value;
use std::sync::Arc;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::process::{ChildStdin, ChildStdout};
use tokio::sync::Mutex;
use tracing::{error, info, warn};

use crate::runtime::{PihuRuntime, PihuState};

pub struct RustIpc {
    runtime: PihuRuntime,
    stdin: Option<Arc<Mutex<ChildStdin>>>,
}

impl RustIpc {
    pub fn new(runtime: PihuRuntime) -> Self {
        Self {
            runtime,
            stdin: None,
        }
    }

    pub fn set_stdin(&mut self, stdin: ChildStdin) {
        self.stdin = Some(Arc::new(Mutex::new(stdin)));
    }

    pub async fn send_command(&self, cmd: &Value) -> Result<(), String> {
        if let Some(stdin) = &self.stdin {
            let mut line = serde_json::to_string(cmd).map_err(|e| e.to_string())?;
            line.push('\n');
            let mut guard = stdin.lock().await;
            guard
                .write_all(line.as_bytes())
                .await
                .map_err(|e| format!("Failed to write to Python stdin: {}", e))?;
            guard
                .flush()
                .await
                .map_err(|e| format!("Failed to flush Python stdin: {}", e))?;
            Ok(())
        } else {
            Err("Python stdin not initialized".to_string())
        }
    }

    pub async fn start_reading(&self, stdout: ChildStdout) {
        let runtime = self.runtime.clone();
        let mut reader = BufReader::new(stdout).lines();

        while let Ok(Some(line)) = reader.next_line().await {
            let trimmed = line.trim();
            if trimmed.is_empty() {
                continue;
            }

            match serde_json::from_str::<Value>(trimmed) {
                Ok(val) => {
                    self.handle_event(val, &runtime).await;
                }
                Err(err) => {
                    warn!("Non-JSON message from Python stdout: '{}' ({})", trimmed, err);
                }
            }
        }
        info!("Python stdout stream closed.");
    }

    async fn handle_event(&self, val: Value, runtime: &PihuRuntime) {
        let event_type = match val.get("type").and_then(|v| v.as_str()) {
            Some(t) => t,
            None => {
                warn!("Received event without 'type': {:?}", val);
                return;
            }
        };

        match event_type {
            "ready" => {
                info!("[PIHU][RUNTIME] Python AI runtime is ready.");
                runtime.emit_event("python_ready", &val);
            }
            "wake_detected" => {
                info!("[PIHU][STATE] Wake detected: {:?}", val);
                runtime.transition_to(PihuState::WakeDetected).await;
                runtime.emit_event("wake_detected", &val);
                // Immediately transition to Listening
                runtime.transition_to(PihuState::Listening).await;
            }
            "audio_level" => {
                runtime.emit_event("audio_level", &val);
            }
            "speech_started" => {
                info!("[PIHU][VAD] Speech started");
                runtime.emit_event("speech_started", &val);
            }
            "speech_ended" => {
                info!("[PIHU][VAD] Speech ended");
                runtime.emit_event("speech_ended", &val);
            }
            "transcription_started" => {
                info!("[PIHU][STATE] Transcription started");
                runtime.transition_to(PihuState::Transcribing).await;
                runtime.emit_event("transcription_started", &val);
            }
            "transcription_completed" => {
                let text = val.get("text").and_then(|v| v.as_str()).unwrap_or("");
                info!("[PIHU][STT] Transcription: '{}'", text);
                runtime.transition_to(PihuState::Thinking).await;
                runtime.emit_event("transcription_completed", &val);
            }
            "intent_detected" => {
                info!("[PIHU][INTENT] Intent: {:?}", val);
                runtime.emit_event("intent_detected", &val);
            }
            "planning_started" => {
                runtime.transition_to(PihuState::Planning).await;
                runtime.emit_event("planning_started", &val);
            }
            "planning_completed" => {
                runtime.emit_event("planning_completed", &val);
            }
            "tool_started" => {
                info!("[PIHU][MCP] Tool started: {:?}", val);
                runtime.transition_to(PihuState::Executing).await;
                runtime.emit_event("tool_started", &val);
            }
            "tool_completed" => {
                info!("[PIHU][MCP] Tool completed: {:?}", val);
                runtime.emit_event("tool_completed", &val);
            }
            "tts_started" => {
                info!("[PIHU][TTS] Speech playback started");
                runtime.transition_to(PihuState::Responding).await;
                runtime.emit_event("tts_started", &val);
            }
            "tts_completed" => {
                info!("[PIHU][TTS] Speech playback finished");
                runtime.emit_event("tts_completed", &val);
            }
            "idle" => {
                runtime.transition_to(PihuState::Idle).await;
            }
            "timeout" => {
                info!("[PIHU][VAD] Interaction timed out, returning to IDLE");
                runtime.transition_to(PihuState::Idle).await;
                runtime.emit_event("timeout", &val);
            }
            "error" => {
                error!("[PIHU][ERROR] Subsystem error: {:?}", val);
                runtime.transition_to(PihuState::Error).await;
                runtime.emit_event("error", &val);
            }
            _ => {
                info!("Unhandled event: {}", event_type);
                runtime.emit_event(event_type, &val);
            }
        }
    }
}
