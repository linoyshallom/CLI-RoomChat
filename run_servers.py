import subprocess
import sys
import threading
import time

SERVER_MODULES = [
    "server.server_chat",
    "server.server_file_transfer",
]

# label + ANSI color per module, so interleaved output from both servers stays easy to tell apart
LABELS = {
    "server.server_chat": ("chat", "\033[36m"),           # cyan
    "server.server_file_transfer": ("files", "\033[35m"),  # magenta
}
RESET = "\033[0m"

print_lock = threading.Lock()


def stream_output(module: str, proc: subprocess.Popen) -> None:
    label, color = LABELS.get(module, (module, ""))
    for line in proc.stdout:
        with print_lock:
            print(f"{color}[{label}]{RESET} {line.rstrip()}")


def main():
    processes = {}
    for module in SERVER_MODULES:
        proc = subprocess.Popen(
            [sys.executable, "-m", module],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        processes[module] = proc
        threading.Thread(target=stream_output, args=(module, proc), daemon=True).start()

    label_list = ", ".join(LABELS.get(m, (m, ""))[0] for m in processes)
    print(f"Started {len(processes)} servers: {label_list} (Ctrl+C to stop)")

    try:
        while True:
            for module, proc in processes.items():
                exit_code = proc.poll()
                if exit_code is not None:
                    print(f"\n{module} exited unexpectedly (code {exit_code}), stopping the rest...")
                    raise SystemExit(1)
            time.sleep(0.5)

    except (KeyboardInterrupt, SystemExit):
        print("\nStopping servers...")

    finally:
        for proc in processes.values():
            if proc.poll() is None:
                proc.terminate()
        for proc in processes.values():
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    main()
