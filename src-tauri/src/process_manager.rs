use std::path::PathBuf;
use std::process::Stdio;
use std::sync::Arc;
use std::time::Duration;
use tokio::process::{Child, Command};
use tokio::sync::Mutex;
use tracing::{error, info};

use crate::ipc::RustIpc;
use crate::runtime::{PihuRuntime, PihuState};

pub struct ProcessManager {
    runtime: PihuRuntime,
    ipc: Arc<Mutex<RustIpc>>,
    child: Arc<Mutex<Option<Child>>>,
    config_path: PathBuf,
    project_root: PathBuf,
    is_shutting_down: Arc<Mutex<bool>>,
}

impl ProcessManager {
    pub fn new(runtime: PihuRuntime, ipc: Arc<Mutex<RustIpc>>, config_path: PathBuf) -> Self {
        // The binary lives at <project_root>/src-tauri/target/debug/pihu-runtime
        // Walk up 3 parent levels to reach the project root.
        let project_root = std::env::current_exe()
            .ok()
            .and_then(|exe| {
                exe.parent()        // .../target/debug/
                    .and_then(|p| p.parent())   // .../target/
                    .and_then(|p| p.parent())   // .../src-tauri/
                    .and_then(|p| p.parent())   // project root
                    .map(|p| p.to_path_buf())
            })
            .unwrap_or_else(|| {
                // Fallback: CWD-based (useful during `cargo run` from project root)
                std::env::current_dir()
                    .ok()
                    .and_then(|cwd| {
                        if cwd.ends_with("src-tauri") {
                            cwd.parent().map(|p| p.to_path_buf())
                        } else {
                            Some(cwd)
                        }
                    })
                    .unwrap_or_else(|| PathBuf::from("."))
            });

        info!("[PIHU][RUNTIME] Project root: {:?}", project_root);

        // Resolve config_path relative to project root if not absolute
        let config_path = if config_path.is_absolute() {
            config_path
        } else {
            project_root.join(&config_path)
        };

        Self {
            runtime,
            ipc,
            child: Arc::new(Mutex::new(None)),
            config_path,
            project_root,
            is_shutting_down: Arc::new(Mutex::new(false)),
        }
    }

    /// Search for the project's .venv Python first (absolute paths), then fall back to system.
    fn find_python_executable(&self) -> PathBuf {
        // Prefer the project's own venv — has all required packages installed
        let venv_candidates = [
            self.project_root.join(".venv/bin/python"),
            self.project_root.join(".venv/bin/python3"),
            self.project_root.join(".venv/bin/python3.11"),
            self.project_root.join(".venv/bin/python3.10"),
        ];
        for path in &venv_candidates {
            if path.exists() {
                info!("[PIHU][RUNTIME] Python binary (venv): {:?}", path);
                return path.clone();
            }
        }

        // System-wide fallback (absolute paths on macOS/Linux)
        let system_candidates = [
            "/opt/homebrew/bin/python3.11",
            "/opt/homebrew/bin/python3.10",
            "/opt/homebrew/bin/python3",
            "/usr/local/bin/python3",
            "/usr/bin/python3",
        ];
        for candidate in &system_candidates {
            if PathBuf::from(candidate).exists() {
                info!("[PIHU][RUNTIME] Python binary (system fallback): {}", candidate);
                return PathBuf::from(candidate);
            }
        }

        info!("[PIHU][RUNTIME] Python binary: python3 (PATH lookup)");
        PathBuf::from("python3")
    }

    pub async fn start(&self) -> Result<(), String> {
        let python_bin = self.find_python_executable();
        let main_py = self.project_root.join("python").join("main.py");

        info!("[PIHU][RUNTIME] Spawning Python AI subprocess");
        info!("[PIHU][RUNTIME]   Binary : {:?}", python_bin);
        info!("[PIHU][RUNTIME]   Script : {:?}", main_py);
        info!("[PIHU][RUNTIME]   Config : {:?}", self.config_path);
        info!("[PIHU][RUNTIME]   CWD    : {:?}", self.project_root);

        if !main_py.exists() {
            return Err(format!(
                "python/main.py not found at {:?}. Project root resolved to {:?}.",
                main_py, self.project_root
            ));
        }

        let mut cmd = Command::new(&python_bin);
        cmd.arg(&main_py)
            .arg("--config")
            .arg(&self.config_path)
            .env("PYTHONUNBUFFERED", "1")
            .env("PYTHONPATH", &self.project_root)
            .current_dir(&self.project_root)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit());

        let mut child = cmd
            .spawn()
            .map_err(|e| format!("Failed to spawn Python ({:?}): {}", python_bin, e))?;

        let stdin = child
            .stdin
            .take()
            .ok_or_else(|| "Failed to capture Python stdin".to_string())?;
        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| "Failed to capture Python stdout".to_string())?;

        {
            let mut ipc_guard = self.ipc.lock().await;
            ipc_guard.set_stdin(stdin);
        }

        // Start IPC reader in Tauri's runtime
        let ipc_clone = self.ipc.clone();
        tauri::async_runtime::spawn(async move {
            let guard = ipc_clone.lock().await;
            guard.start_reading(stdout).await;
        });

        let mut child_guard = self.child.lock().await;
        *child_guard = Some(child);

        // Watchdog: poll child exit status every 500ms
        let child_arc = self.child.clone();
        let runtime = self.runtime.clone();
        let is_shutting_down = self.is_shutting_down.clone();

        tauri::async_runtime::spawn(async move {
            loop {
                tokio::time::sleep(Duration::from_millis(500)).await;
                let mut guard = child_arc.lock().await;
                if let Some(child_proc) = guard.as_mut() {
                    match child_proc.try_wait() {
                        Ok(Some(status)) => {
                            let shutting_down = *is_shutting_down.lock().await;
                            if !shutting_down {
                                error!(
                                    "[PIHU][RUNTIME] Python AI process exited unexpectedly: {}",
                                    status
                                );
                                runtime.transition_to(PihuState::Error).await;
                            } else {
                                info!(
                                    "[PIHU][RUNTIME] Python AI process terminated normally ({})",
                                    status
                                );
                            }
                            *guard = None;
                            break;
                        }
                        Ok(None) => {} // still running
                        Err(e) => {
                            error!("[PIHU][RUNTIME] Watchdog error: {}", e);
                            break;
                        }
                    }
                } else {
                    break;
                }
            }
        });

        Ok(())
    }

    pub async fn shutdown(&self) {
        info!("[PIHU][RUNTIME] Shutting down Python AI subprocess...");
        {
            let mut sd = self.is_shutting_down.lock().await;
            *sd = true;
        }
        let mut guard = self.child.lock().await;
        if let Some(mut child) = guard.take() {
            let _ = child.kill().await;
        }
    }

    pub async fn restart(&self) -> Result<(), String> {
        info!("[PIHU][RUNTIME] Restarting Python AI subprocess...");
        self.shutdown().await;
        tokio::time::sleep(Duration::from_millis(500)).await;
        {
            let mut sd = self.is_shutting_down.lock().await;
            *sd = false;
        }
        self.start().await
    }
}
