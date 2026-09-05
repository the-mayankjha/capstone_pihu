use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tauri::{AppHandle, Emitter};
use tokio::sync::RwLock;
use tracing::{info, warn};

/// Authoritative PIHU States
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum PihuState {
    Idle,
    WakeDetected,
    Listening,
    Transcribing,
    Thinking,
    Planning,
    Executing,
    Responding,
    Error,
}

impl std::fmt::Display for PihuState {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let s = match self {
            PihuState::Idle => "IDLE",
            PihuState::WakeDetected => "WAKE_DETECTED",
            PihuState::Listening => "LISTENING",
            PihuState::Transcribing => "TRANSCRIBING",
            PihuState::Thinking => "THINKING",
            PihuState::Planning => "PLANNING",
            PihuState::Executing => "EXECUTING",
            PihuState::Responding => "RESPONDING",
            PihuState::Error => "ERROR",
        };
        write!(f, "{}", s)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StateChangedPayload {
    pub state: PihuState,
    pub previous_state: PihuState,
    pub timestamp: u64,
}

#[derive(Clone)]
pub struct PihuRuntime {
    state: Arc<RwLock<PihuState>>,
    app_handle: AppHandle,
}

impl PihuRuntime {
    pub fn new(app_handle: AppHandle) -> Self {
        Self {
            state: Arc::new(RwLock::new(PihuState::Idle)),
            app_handle,
        }
    }

    pub async fn get_state(&self) -> PihuState {
        *self.state.read().await
    }

    pub async fn transition_to(&self, new_state: PihuState) {
        let mut current = self.state.write().await;
        if *current == new_state {
            return;
        }

        let prev = *current;
        *current = new_state;

        info!("[PIHU][STATE] {} → {}", prev, new_state);

        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_millis() as u64;

        let payload = StateChangedPayload {
            state: new_state,
            previous_state: prev,
            timestamp: now,
        };

        if let Err(e) = self.app_handle.emit("state_changed", &payload) {
            warn!("Failed to emit state_changed event to frontend: {:?}", e);
        }
    }

    pub fn emit_event<T: Serialize + Clone>(&self, event_name: &str, payload: &T) {
        if let Err(e) = self.app_handle.emit(event_name, payload) {
            warn!("Failed to emit '{}' event: {:?}", event_name, e);
        }
    }
}
