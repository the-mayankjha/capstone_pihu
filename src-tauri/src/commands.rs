use serde_json::json;
use serde::Serialize;
use std::sync::Arc;
use tauri::{AppHandle, Manager, State};
use tokio::sync::Mutex;
use tracing::info;

use crate::ipc::RustIpc;
use crate::process_manager::ProcessManager;
use crate::runtime::{PihuRuntime, PihuState};

pub struct AppState {
    pub runtime: PihuRuntime,
    pub ipc: Arc<Mutex<RustIpc>>,
    pub process_manager: Arc<ProcessManager>,
}

#[tauri::command]
pub async fn get_state(state: State<'_, AppState>) -> Result<PihuState, String> {
    Ok(state.runtime.get_state().await)
}

#[tauri::command]
pub async fn dev_trigger_state(
    target_state: String,
    state: State<'_, AppState>,
) -> Result<String, String> {
    let parsed = match target_state.to_uppercase().as_str() {
        "IDLE" => PihuState::Idle,
        "WAKE_DETECTED" => PihuState::WakeDetected,
        "LISTENING" => PihuState::Listening,
        "TRANSCRIBING" => PihuState::Transcribing,
        "THINKING" => PihuState::Thinking,
        "PLANNING" => PihuState::Planning,
        "EXECUTING" => PihuState::Executing,
        "RESPONDING" => PihuState::Responding,
        "ERROR" => PihuState::Error,
        _ => return Err(format!("Invalid state: {}", target_state)),
    };

    info!("[DEV] Manually triggering state: {:?}", parsed);
    state.runtime.transition_to(parsed).await;
    Ok(format!("Transitioned to {:?}", parsed))
}

#[tauri::command]
pub async fn dev_simulate_command(
    text: String,
    state: State<'_, AppState>,
) -> Result<String, String> {
    info!("[DEV] Simulating voice command: '{}'", text);
    let cmd = json!({
        "type": "simulate_command",
        "text": text
    });
    let ipc = state.ipc.lock().await;
    ipc.send_command(&cmd).await?;
    Ok("Command dispatched to Python AI runtime".to_string())
}

#[tauri::command]
pub async fn dev_trigger_wake(
    wake_word: Option<String>,
    state: State<'_, AppState>,
) -> Result<String, String> {
    let word = wake_word.unwrap_or_else(|| "hey_pihu".to_string());
    info!("[DEV] Simulating wake word: '{}'", word);
    let cmd = json!({
        "type": "trigger_wake",
        "wake_word": word
    });
    let ipc = state.ipc.lock().await;
    ipc.send_command(&cmd).await?;
    Ok("Wake event dispatched to Python AI runtime".to_string())
}

#[tauri::command]
pub async fn restart_python(state: State<'_, AppState>) -> Result<String, String> {
    info!("[DEV] Requesting Python process restart...");
    state.process_manager.restart().await?;
    Ok("Python runtime restarted successfully".to_string())
}

#[tauri::command]
pub fn set_ignore_cursor_events(app: tauri::AppHandle, ignore: bool) -> Result<(), String> {
    if let Some(window) = app.get_webview_window("main") {
        window.set_ignore_cursor_events(ignore).map_err(|e| e.to_string())?;
    }
    Ok(())
}
