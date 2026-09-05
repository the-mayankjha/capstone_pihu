#!/usr/bin/env python3
"""
PIHU Project Setup Script
=========================
Automates the full end-to-end project environment setup.

Usage:
    python setup.py               # Full setup (all steps)
    python setup.py --help        # Show all available flags

Flags:
    --skip-brew        Skip Homebrew system dependency installation
    --skip-rust        Skip Rust toolchain installation
    --skip-node        Skip Node.js npm install
    --skip-python      Skip Python virtual environment & package installation
    --skip-models      Skip Silero VAD & faster-whisper model downloads
    --skip-build       Skip final Tauri/Rust cargo check
    --check            Verify all prerequisites are already installed (dry-run)
    --clean            Delete .venv, node_modules, and Rust target/ before setup

Author: PIHU Engineering Team
"""

import os
import sys
import shutil
import argparse
import platform
import subprocess
import urllib.request
from pathlib import Path

# ─────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
PYTHON = VENV / "bin" / "python"
PIP = VENV / "bin" / "pip"
REQUIREMENTS = ROOT / "python" / "requirements.txt"
MODELS_DIR = ROOT / "models" / "wakeUp"
REPORTS_DIR = ROOT / "reports"

MIN_PYTHON = (3, 10)
MIN_NODE = (18, 0)
IS_MACOS = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"

# Silero VAD v5 ONNX — official Snakers4 release
SILERO_VAD_URL = (
    "https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx"
)
SILERO_VAD_DST = MODELS_DIR / "silero_vad.onnx"

# ─────────────────────────────────────────────────────────────────
# Console Helpers
# ─────────────────────────────────────────────────────────────────

CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"

def banner(text: str):
    width = 76
    print(f"\n{CYAN}{'═' * width}{RESET}")
    print(f"{CYAN}  {BOLD}{text}{RESET}")
    print(f"{CYAN}{'═' * width}{RESET}")

def step(text: str):
    print(f"\n{BOLD}[PIHU SETUP]{RESET} {text}")

def ok(text: str):
    print(f"  {GREEN}✓{RESET} {text}")

def warn(text: str):
    print(f"  {YELLOW}⚠{RESET}  {text}")

def fail(text: str):
    print(f"  {RED}✗{RESET}  {text}")

def info(text: str):
    print(f"  {CYAN}→{RESET}  {text}")

def abort(text: str):
    print(f"\n{RED}{BOLD}FATAL:{RESET} {text}")
    sys.exit(1)


# ─────────────────────────────────────────────────────────────────
# Shell Helpers
# ─────────────────────────────────────────────────────────────────

def run(cmd: list, cwd: Path = ROOT, check: bool = True, capture: bool = False, env: dict = None) -> subprocess.CompletedProcess:
    """Run a command, stream output, optionally capture it."""
    env_full = {**os.environ, **(env or {})}
    result = subprocess.run(
        cmd,
        cwd=str(cwd),
        check=False,
        capture_output=capture,
        text=True,
        env=env_full,
    )
    if check and result.returncode != 0:
        if capture:
            print(result.stderr or result.stdout or "")
        abort(f"Command failed (exit {result.returncode}): {' '.join(str(c) for c in cmd)}")
    return result


def which(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def get_version(cmd: list) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return (r.stdout + r.stderr).strip().split("\n")[0]
    except Exception:
        return "unknown"


# ─────────────────────────────────────────────────────────────────
# Step 0 — Sanity Check: Python version
# ─────────────────────────────────────────────────────────────────

def check_python_version():
    step("Checking Python version...")
    v = sys.version_info
    if (v.major, v.minor) < MIN_PYTHON:
        abort(
            f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ is required. "
            f"You have Python {v.major}.{v.minor}.{v.micro}.\n"
            "  → Download from: https://www.python.org/downloads/"
        )
    ok(f"Python {v.major}.{v.minor}.{v.micro}")


# ─────────────────────────────────────────────────────────────────
# Step 1 — Clean (optional)
# ─────────────────────────────────────────────────────────────────

def clean_artifacts():
    step("Cleaning existing build artifacts...")
    targets = [
        ROOT / ".venv",
        ROOT / "node_modules",
        ROOT / "dist",
        ROOT / "src-tauri" / "target",
        ROOT / ".pytest_cache",
    ]
    for p in targets:
        if p.exists():
            info(f"Removing {p.relative_to(ROOT)}")
            shutil.rmtree(p, ignore_errors=True)
    ok("Clean complete.")


# ─────────────────────────────────────────────────────────────────
# Step 2 — Homebrew system dependencies (macOS only)
# ─────────────────────────────────────────────────────────────────

BREW_PACKAGES = [
    ("portaudio",  "portaudio",   "Required by sounddevice for real-time audio I/O"),
    ("ffmpeg",     "ffmpeg",      "Required by faster-whisper audio decoding"),
    ("node",       "node",        "Node.js JavaScript runtime for Vite/npm"),
]

def setup_brew():
    if not IS_MACOS:
        warn("Homebrew step skipped (not macOS).")
        return

    step("Installing system dependencies via Homebrew...")

    if not which("brew"):
        warn("Homebrew not found. Installing Homebrew...")
        info("Running: /bin/bash -c $(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)")
        run(
            ["/bin/bash", "-c",
             'curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh | bash'],
            check=True,
        )
    else:
        ok(f"Homebrew: {get_version(['brew', '--version'])}")

    for pkg, binary, desc in BREW_PACKAGES:
        if which(binary):
            ok(f"{pkg} already installed ({get_version([binary, '--version'])})")
        else:
            info(f"Installing {pkg} — {desc}...")
            run(["brew", "install", pkg])
            ok(f"{pkg} installed.")


# ─────────────────────────────────────────────────────────────────
# Step 3 — Rust toolchain
# ─────────────────────────────────────────────────────────────────

def setup_rust():
    step("Checking Rust toolchain...")
    if which("rustc") and which("cargo"):
        ok(f"Rust: {get_version(['rustc', '--version'])}")
        ok(f"Cargo: {get_version(['cargo', '--version'])}")
    else:
        warn("Rust not found. Installing via rustup...")
        info("Running: curl https://sh.rustup.rs -sSf | sh -s -- -y")
        run(
            ["/bin/bash", "-c",
             "curl https://sh.rustup.rs -sSf | sh -s -- -y --no-modify-path"],
            check=True,
        )
        # Source cargo env
        cargo_env = Path.home() / ".cargo" / "env"
        if cargo_env.exists():
            info("Sourcing $HOME/.cargo/env into current session...")

        cargo_bin = str(Path.home() / ".cargo" / "bin")
        os.environ["PATH"] = cargo_bin + os.pathsep + os.environ.get("PATH", "")
        ok("Rust installed successfully.")

    # Ensure stable toolchain
    info("Checking Rust stable toolchain...")
    run(["rustup", "toolchain", "install", "stable", "--no-self-update"], check=False)
    run(["rustup", "default", "stable"], check=False)

    if IS_MACOS:
        info("Adding macOS cross-compilation targets...")
        run(["rustup", "target", "add", "aarch64-apple-darwin"], check=False)
        run(["rustup", "target", "add", "x86_64-apple-darwin"], check=False)

    ok("Rust toolchain ready.")


# ─────────────────────────────────────────────────────────────────
# Step 4 — Node.js / npm
# ─────────────────────────────────────────────────────────────────

def setup_node():
    step("Checking Node.js / npm...")
    if not which("node"):
        if IS_MACOS:
            warn("Node.js not found. Install it via: brew install node")
        else:
            warn("Node.js not found. Install from: https://nodejs.org/")
        abort(
            "Node.js 18+ is required. Please install it and rerun setup.py.\n"
            "  macOS: brew install node\n"
            "  Linux: https://nodejs.org/en/download/package-manager/"
        )

    # Check version
    node_version_str = get_version(["node", "--version"]).lstrip("v")
    major = int(node_version_str.split(".")[0]) if node_version_str[0].isdigit() else 0
    if major < MIN_NODE[0]:
        abort(f"Node.js {MIN_NODE[0]}+ required (found {node_version_str}). Please upgrade.")

    ok(f"Node.js: v{node_version_str}")
    ok(f"npm: {get_version(['npm', '--version'])}")

    step("Installing npm dependencies...")
    run(["npm", "install"])
    ok("npm packages installed.")


# ─────────────────────────────────────────────────────────────────
# Step 5 — Python Virtual Environment & Packages
# ─────────────────────────────────────────────────────────────────

def setup_python():
    step("Setting up Python virtual environment...")

    if VENV.exists():
        info(".venv already exists — skipping creation.")
    else:
        info(f"Creating .venv with {sys.executable} ...")
        run([sys.executable, "-m", "venv", str(VENV)])
        ok(".venv created.")

    if not PYTHON.exists():
        abort(
            f"Virtual environment Python not found at: {PYTHON}\n"
            "Please delete .venv and rerun setup.py."
        )

    # Upgrade pip & wheel first
    step("Upgrading pip, setuptools, wheel...")
    run([str(PIP), "install", "--upgrade", "pip", "setuptools", "wheel", "--quiet"])
    ok("pip upgraded.")

    # Install project requirements
    step("Installing Python project requirements...")
    info(f"Source: {REQUIREMENTS}")
    run([str(PIP), "install", "-r", str(REQUIREMENTS)])
    ok("All Python packages installed.")

    # Verify key imports
    step("Verifying Python package imports...")
    checks = [
        ("numpy",          "import numpy; print(numpy.__version__)"),
        ("onnxruntime",    "import onnxruntime; print(onnxruntime.__version__)"),
        ("openwakeword",   "import openwakeword; print('ok')"),
        ("sounddevice",    "import sounddevice; print('ok')"),
        ("faster-whisper", "from faster_whisper import WhisperModel; print('ok')"),
    ]
    all_ok = True
    for name, code in checks:
        r = run([str(PYTHON), "-c", code], check=False, capture=True)
        if r.returncode == 0:
            ok(f"{name}: {r.stdout.strip()}")
        else:
            fail(f"{name}: FAILED — {r.stderr.strip()}")
            all_ok = False
    if not all_ok:
        abort("Some Python packages failed to import. Check errors above.")


# ─────────────────────────────────────────────────────────────────
# Step 6 — Download / Verify AI Models
# ─────────────────────────────────────────────────────────────────

WAKE_MODELS = [
    ("Gen-pihu.onnx",       None,  "Generalized PIHU wake word model"),
    ("hey_pihu.onnx",       None,  "Phrase: 'Hey PIHU'"),
    ("hey_pihu.onnx.data",  None,  "Weights for hey_pihu"),
    ("hi_pihu.onnx",        None,  "Phrase: 'Hi PIHU'"),
    ("hi_pihu.onnx.data",   None,  "Weights for hi_pihu"),
    ("pihu.onnx",           None,  "Name: 'PIHU'"),
    ("pihu.onnx.data",      None,  "Weights for pihu"),
    ("pihu(g).onnx.data",   None,  "Weights for Gen-pihu"),
]


def download_file(url: str, dst: Path, desc: str):
    """Download file with progress bar."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    print(f"  {CYAN}↓{RESET}  Downloading {desc}...")

    def reporthook(blocknum, blocksize, totalsize):
        downloaded = blocknum * blocksize
        if totalsize > 0:
            pct = min(100, int(downloaded * 100 / totalsize))
            filled = pct // 4
            bar = "█" * filled + "░" * (25 - filled)
            mb = downloaded / (1024 * 1024)
            total_mb = totalsize / (1024 * 1024)
            print(f"\r    [{bar}] {pct:3d}%  {mb:.1f}/{total_mb:.1f} MB", end="", flush=True)
        else:
            print(f"\r    {downloaded // 1024} KB downloaded...", end="", flush=True)

    urllib.request.urlretrieve(url, str(dst), reporthook=reporthook)
    print()


def setup_models():
    step("Checking & downloading AI models...")
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Silero VAD ONNX
    if SILERO_VAD_DST.exists() and SILERO_VAD_DST.stat().st_size > 1_000_000:
        ok(f"silero_vad.onnx already present ({SILERO_VAD_DST.stat().st_size // 1024} KB)")
    else:
        try:
            download_file(SILERO_VAD_URL, SILERO_VAD_DST, "Silero VAD v5 ONNX")
            ok(f"silero_vad.onnx downloaded ({SILERO_VAD_DST.stat().st_size // 1024} KB)")
        except Exception as e:
            warn(f"Could not auto-download silero_vad.onnx: {e}")
            warn("Download manually from: https://github.com/snakers4/silero-vad")
            warn(f"Place it at: {SILERO_VAD_DST}")

    # 2. OpenWakeWord custom PIHU models
    missing = []
    for filename, url, desc in WAKE_MODELS:
        dst = MODELS_DIR / filename
        if dst.exists() and dst.stat().st_size > 1000:
            ok(f"{filename} ({dst.stat().st_size // 1024} KB)")
        else:
            missing.append((filename, url, desc))

    if missing:
        print()
        warn("The following PIHU wake-word models are MISSING:")
        for filename, _, desc in missing:
            print(f"    {RED}✗{RESET}  {filename} — {desc}")
        print()
        warn("These are custom models trained for PIHU wake phrases.")
        warn("They must be placed in: models/wakeUp/")
        warn("If you have the model files, copy them to that directory and rerun setup.py.")
        warn("For training your own models, see: https://github.com/dscripka/openWakeWord")
    else:
        ok("All PIHU wake-word models present.")

    # 3. Pre-download faster-whisper model (tiny.en cache warm)
    step("Pre-downloading faster-whisper STT model (tiny.en)...")
    warmup_code = """
from faster_whisper import WhisperModel
import os
print("Loading faster-whisper tiny.en model...")
m = WhisperModel("tiny.en", device="cpu", compute_type="int8")
print("faster-whisper model ready.")
"""
    r = run([str(PYTHON), "-c", warmup_code], check=False, capture=True)
    if r.returncode == 0:
        ok("faster-whisper tiny.en model cached & ready.")
    else:
        warn(f"faster-whisper model warm-up failed: {r.stderr.strip()[:200]}")
        warn("It will be downloaded automatically on first use.")


# ─────────────────────────────────────────────────────────────────
# Step 7 — Tauri / Cargo check
# ─────────────────────────────────────────────────────────────────

def setup_tauri_build():
    step("Running Cargo check on Tauri runtime...")
    tauri_dir = ROOT / "src-tauri"
    r = run(["cargo", "check", "--manifest-path", str(tauri_dir / "Cargo.toml")], check=False, capture=True)
    if r.returncode == 0:
        ok("Tauri Rust runtime compiled successfully.")
    else:
        warn("Cargo check produced warnings/errors:")
        print(r.stderr[-2000:])
        warn("Run 'cargo build' in src-tauri/ manually to see full output.")


# ─────────────────────────────────────────────────────────────────
# Step 8 — Smoke test: Python PIHU imports
# ─────────────────────────────────────────────────────────────────

def smoke_test():
    step("Running PIHU module smoke test...")
    smoke = """
import sys
sys.path.insert(0, '.')
errors = []
modules = [
    ("python.audio.capture",        "AudioCapture"),
    ("python.vad.silero",           "SileroVad"),
    ("python.wakeword.engine",      "WakeWordEngine"),
    ("python.stt.recognizer",       "create_speech_recognizer"),
    ("python.intelligence.intent",  "IntentEngine"),
    ("python.intelligence.planner", "Planner"),
    ("python.mcp.client",           "MCPClient"),
    ("python.mcp.tools",            "ToolRegistry"),
    ("python.tts.engine",           "create_tts_engine"),
    ("python.ipc.protocol",         "IPCProtocol"),
]
for module_path, symbol in modules:
    try:
        mod = __import__(module_path, fromlist=[symbol])
        getattr(mod, symbol)
        print(f"  OK  {module_path}.{symbol}")
    except Exception as e:
        errors.append(f"  FAIL {module_path}.{symbol}: {e}")

if errors:
    for e in errors:
        print(e, file=sys.stderr)
    sys.exit(1)
print("ALL OK")
"""
    r = run([str(PYTHON), "-c", smoke], cwd=ROOT, check=False, capture=True)
    if r.returncode == 0:
        for line in r.stdout.strip().split("\n"):
            if line.startswith("  OK"):
                ok(line.strip().replace("OK  ", ""))
            elif line == "ALL OK":
                pass
        ok("All PIHU Python modules imported successfully.")
    else:
        warn("Some PIHU modules failed to import:")
        print(r.stderr)


# ─────────────────────────────────────────────────────────────────
# Step 9 — Print final usage summary
# ─────────────────────────────────────────────────────────────────

def print_summary(args):
    print(f"\n{CYAN}{'═' * 76}{RESET}")
    print(f"{CYAN}  {BOLD}PIHU Setup Complete!{RESET}")
    print(f"{CYAN}{'═' * 76}{RESET}")
    print()
    print(f"  {BOLD}Start Desktop Application:{RESET}")
    print(f"    npm run tauri dev")
    print()
    print(f"  {BOLD}Run PIHU Diagnostic CLI:{RESET}")
    print(f"    PYTHONPATH=. .venv/bin/python pihu.py --help")
    print()
    print(f"  {BOLD}Quick Mode Reference:{RESET}")
    print(f"    --detect          Real-time wake word detection from microphone")
    print(f"    --detect --full   Wake detection + full voice interaction pipeline")
    print(f"    --file <wav>      Analyse a WAV file for wake word events")
    print(f"    --live            Live VU meter + model score bars")
    print(f"    --benchmark       Latency percentile benchmark across all models")
    print(f"    --matrix          Noise immunity & threshold sensitivity matrix")
    print()
    print(f"  {BOLD}Run Unit Tests:{RESET}")
    print(f"    PYTHONPATH=. .venv/bin/pytest tests/ -v")
    print()
    print(f"  {CYAN}{'─' * 76}{RESET}")
    print()


# ─────────────────────────────────────────────────────────────────
# Prerequisites Check (dry-run)
# ─────────────────────────────────────────────────────────────────

def check_prerequisites():
    banner("PIHU Environment Prerequisites Check")
    issues = []

    checks = [
        ("python3",     ["python3", "--version"],      f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+"),
        ("rustc",       ["rustc", "--version"],         "Rust (rustc 1.75+)"),
        ("cargo",       ["cargo", "--version"],         "Cargo"),
        ("node",        ["node", "--version"],           f"Node.js {MIN_NODE[0]}+"),
        ("npm",         ["npm", "--version"],            "npm"),
        ("portaudio",   ["brew", "list", "portaudio"],  "PortAudio"),
    ]

    for binary, cmd, desc in checks:
        if which(binary) or which(cmd[0]):
            ver = get_version(cmd)
            ok(f"{desc}: {ver}")
        else:
            fail(f"{desc}: NOT FOUND")
            issues.append(desc)

    venv_ok = PYTHON.exists()
    if venv_ok:
        ok(f"Python venv: {VENV}")
    else:
        fail("Python venv: NOT FOUND — run setup.py to create")
        issues.append("venv")

    models_ok = SILERO_VAD_DST.exists()
    if models_ok:
        ok(f"silero_vad.onnx: {SILERO_VAD_DST.stat().st_size // 1024} KB")
    else:
        fail("silero_vad.onnx: MISSING — run setup.py to download")
        issues.append("silero_vad")

    wake_count = sum(1 for f, _, _ in WAKE_MODELS if (MODELS_DIR / f).exists())
    if wake_count == len(WAKE_MODELS):
        ok(f"Wake-word models: {wake_count}/{len(WAKE_MODELS)} present")
    else:
        warn(f"Wake-word models: {wake_count}/{len(WAKE_MODELS)} present (custom models may be missing)")

    print()
    if issues:
        warn(f"{len(issues)} issue(s) found. Run: python setup.py")
    else:
        ok("All prerequisites satisfied. Run: npm run tauri dev")


# ─────────────────────────────────────────────────────────────────
# Main Entry Point
# ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="python setup.py",
        description="PIHU Project Setup — full environment bootstrapper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:
  python setup.py                   Full end-to-end setup
  python setup.py --check           Verify prerequisites (dry-run, no changes)
  python setup.py --clean           Remove build artifacts, then full setup
  python setup.py --skip-brew       Skip Homebrew dependency installation
  python setup.py --skip-models     Skip model downloads (use existing)
  python setup.py --skip-build      Skip Cargo check (faster iteration)

AFTER SETUP:
  npm run tauri dev                 Launch PIHU desktop application
  PYTHONPATH=. .venv/bin/python pihu.py --detect   Start wake-word detector
""",
    )

    parser.add_argument("--check",        action="store_true", help="Check prerequisites only (dry-run)")
    parser.add_argument("--clean",        action="store_true", help="Delete build artifacts before setup")
    parser.add_argument("--skip-brew",    action="store_true", help="Skip Homebrew system dependencies")
    parser.add_argument("--skip-rust",    action="store_true", help="Skip Rust toolchain setup")
    parser.add_argument("--skip-node",    action="store_true", help="Skip Node.js / npm install")
    parser.add_argument("--skip-python",  action="store_true", help="Skip Python venv & package install")
    parser.add_argument("--skip-models",  action="store_true", help="Skip AI model downloads")
    parser.add_argument("--skip-build",   action="store_true", help="Skip Tauri/Cargo check")

    args = parser.parse_args()

    banner("PIHU AI Desktop Runtime — Project Setup")
    print(f"  {BOLD}Root:{RESET}    {ROOT}")
    print(f"  {BOLD}Python:{RESET}  {sys.version}")
    print(f"  {BOLD}OS:{RESET}      {platform.system()} {platform.release()}")

    if args.check:
        check_prerequisites()
        return

    if args.clean:
        clean_artifacts()

    check_python_version()

    if not args.skip_brew:
        setup_brew()
    else:
        info("Skipping Homebrew step (--skip-brew).")

    if not args.skip_rust:
        setup_rust()
    else:
        info("Skipping Rust setup (--skip-rust).")

    if not args.skip_node:
        setup_node()
    else:
        info("Skipping Node.js/npm step (--skip-node).")

    if not args.skip_python:
        setup_python()
    else:
        info("Skipping Python venv step (--skip-python).")

    if not args.skip_models:
        setup_models()
    else:
        info("Skipping model downloads (--skip-models).")

    if not args.skip_build:
        setup_tauri_build()
    else:
        info("Skipping Tauri/Cargo build check (--skip-build).")

    smoke_test()
    print_summary(args)


if __name__ == "__main__":
    main()
