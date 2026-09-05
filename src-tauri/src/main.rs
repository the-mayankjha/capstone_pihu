#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod commands;
mod ipc;
mod process_manager;
mod runtime;

use std::path::PathBuf;
use std::sync::Arc;
use tauri::Manager;
use tokio::sync::Mutex;
use tracing::info;

use commands::AppState;
use ipc::RustIpc;
use process_manager::ProcessManager;
use runtime::PihuRuntime;

fn main() {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "info,pihu_runtime=debug".into()),
        )
        .init();

    info!("[PIHU][RUNTIME] Starting PIHU Core Desktop Runtime...");

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            let app_handle = app.handle().clone();
            let runtime = PihuRuntime::new(app_handle.clone());
            let ipc = Arc::new(Mutex::new(RustIpc::new(runtime.clone())));

            let config_path = PathBuf::from("config/pihu.toml");
            let process_manager = Arc::new(ProcessManager::new(
                runtime.clone(),
                ipc.clone(),
                config_path,
            ));

            app.manage(AppState {
                runtime,
                ipc,
                process_manager: process_manager.clone(),
            });

            // Start Python AI Subprocess in Tauri's async runtime (NOT raw tokio::spawn)
            let pm_clone = process_manager.clone();
            tauri::async_runtime::spawn(async move {
                if let Err(e) = pm_clone.start().await {
                    tracing::error!("[PIHU][RUNTIME] Failed to start Python process: {}", e);
                }
            });

            // Set up main window properties
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.set_always_on_top(true);
                let _ = window.set_decorations(false);
                let _ = window.set_shadow(false);

                // Set window to exactly fill the primary monitor
                if let Ok(Some(monitor)) = window.primary_monitor() {
                    let size = monitor.size();
                    let _ = window.set_size(*size);
                    let _ = window.set_position(tauri::Position::Physical(tauri::PhysicalPosition { x: 0, y: 0 }));
                }

                // Enable transparent click-through (macOS Private API must be true in config)
                let _ = window.set_ignore_cursor_events(true);
            }

            // Set up System Tray / Menu Bar Icon
            #[cfg(desktop)]
            {
                let _ = app.tray_by_id("main").or_else(|| {
                    tauri::tray::TrayIconBuilder::with_id("main")
                        .build(app)
                        .ok()
                });
            }

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::get_state,
            commands::dev_trigger_state,
            commands::dev_simulate_command,
            commands::dev_trigger_wake,
            commands::restart_python,
            commands::set_ignore_cursor_events,
        ])
        .run(tauri::generate_context!())
        .expect("error while running PIHU Tauri application");
}
