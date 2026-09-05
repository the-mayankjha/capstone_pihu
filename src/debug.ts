import { invoke } from "@tauri-apps/api/core";
import { OrbState, PihuOrb } from "./orb";

export class DebugController {
  private panel: HTMLElement;
  private toggleBtn: HTMLElement;
  private closeBtn: HTMLElement;
  private commandInput: HTMLInputElement;
  private sendCmdBtn: HTMLElement;
  private wakeBtn: HTMLElement;
  private restartPyBtn: HTMLElement;
  private logContainer: HTMLElement;
  public orb: PihuOrb;

  constructor(orb: PihuOrb) {
    this.orb = orb;
    this.panel = document.getElementById("dev-panel")!;
    this.toggleBtn = document.getElementById("dev-toggle-btn")!;
    this.closeBtn = document.getElementById("dev-close-btn")!;
    this.commandInput = document.getElementById("dev-command-input") as HTMLInputElement;
    this.sendCmdBtn = document.getElementById("dev-send-cmd-btn")!;
    this.wakeBtn = document.getElementById("dev-wake-btn")!;
    this.restartPyBtn = document.getElementById("dev-restart-py-btn")!;
    this.logContainer = document.getElementById("dev-log-container")!;

    this.setupListeners();
  }

  private setupListeners() {
    // Toggle modal
    this.toggleBtn.addEventListener("click", () => this.togglePanel());
    this.closeBtn.addEventListener("click", () => this.togglePanel(false));

    // Keyboard shortcut Cmd+D or Ctrl+D
    window.addEventListener("keydown", (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "d") {
        e.preventDefault();
        this.togglePanel();
      }
    });

    // Send command
    this.sendCmdBtn.addEventListener("click", () => this.sendCommand());
    this.commandInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        this.sendCommand();
      }
    });

    // Quick command chips
    document.querySelectorAll(".chip").forEach((chip) => {
      chip.addEventListener("click", (e) => {
        const cmd = (e.target as HTMLElement).getAttribute("data-cmd");
        if (cmd) {
          this.commandInput.value = cmd;
          this.sendCommand();
        }
      });
    });

    // State force buttons
    document.querySelectorAll(".state-btn").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        const state = (e.target as HTMLElement).getAttribute("data-state") as OrbState;
        if (state) {
          try {
            await invoke("dev_trigger_state", { targetState: state });
            this.log("DEV", `Forced state to ${state}`);
          } catch (err) {
            this.log("ERROR", `Failed to force state: ${err}`);
          }
        }
      });
    });

    // Trigger wake
    this.wakeBtn.addEventListener("click", async () => {
      try {
        await invoke("dev_trigger_wake", { wakeWord: "hey_pihu" });
        this.log("DEV", "Triggered wake word");
      } catch (err) {
        this.log("ERROR", `Failed to trigger wake: ${err}`);
      }
    });

    // Restart Python
    this.restartPyBtn.addEventListener("click", async () => {
      try {
        this.log("DEV", "Restarting Python AI runtime...");
        await invoke("restart_python");
        this.log("DEV", "Python AI runtime restarted.");
      } catch (err) {
        this.log("ERROR", `Failed to restart Python: ${err}`);
      }
    });
  }

  public togglePanel(force?: boolean) {
    if (force !== undefined) {
      if (force) this.panel.classList.remove("hidden");
      else this.panel.classList.add("hidden");
    } else {
      this.panel.classList.toggle("hidden");
    }
  }

  private async sendCommand() {
    const text = this.commandInput.value.trim();
    if (!text) return;
    this.commandInput.value = "";

    try {
      this.log("USER", `Simulating voice: "${text}"`);
      await invoke("dev_simulate_command", { text });
    } catch (err) {
      this.log("ERROR", `Failed to simulate command: ${err}`);
    }
  }

  public log(subsystem: string, message: string) {
    const timeStr = new Date().toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
    const row = document.createElement("div");
    row.className = "log-entry";
    row.innerHTML = `<span class="log-time">[${timeStr}]</span> <span class="log-type">[${subsystem}]</span> ${message}`;
    this.logContainer.appendChild(row);
    this.logContainer.scrollTop = this.logContainer.scrollHeight;
  }
}
