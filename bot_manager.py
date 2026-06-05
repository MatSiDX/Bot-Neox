import os
import subprocess
import sys
import threading
import time
from datetime import datetime


ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
BOT_SCRIPT = os.path.join(ROOT_DIR, "bot.py")
DASHBOARD_SCRIPT = os.path.join(ROOT_DIR, "web_dashboard.py")
DASHBOARD_HOST = "127.0.0.1"
DASHBOARD_PORT = "8000"
DASHBOARD_URL = f"http://localhost:{DASHBOARD_PORT}"


class BotManager:
    def __init__(self):
        self.process = None
        self.dashboard_process = None
        self.lock = threading.RLock()

    def log(self, message):
        timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        print(f"[MANAGER {timestamp}] {message}", flush=True)

    def build_env(self):
        env = os.environ.copy()
        current_pythonpath = env.get("PYTHONPATH", "")
        paths = [ROOT_DIR]
        if current_pythonpath:
            paths.append(current_pythonpath)
        env["PYTHONPATH"] = os.pathsep.join(paths)
        return env

    def is_running(self):
        return self.process is not None and self.process.poll() is None

    def is_dashboard_running(self):
        return self.dashboard_process is not None and self.dashboard_process.poll() is None

    def start_dashboard(self):
        if self.is_dashboard_running():
            self.log(f"Dashboard ya esta encendido en {DASHBOARD_URL}")
            return

        os.makedirs(os.path.join(ROOT_DIR, "data"), exist_ok=True)
        dashboard_log = os.path.join(ROOT_DIR, "data", "dashboard.log")
        dashboard_error_log = os.path.join(ROOT_DIR, "data", "dashboard.err")
        with open(dashboard_log, "ab") as stdout, open(dashboard_error_log, "ab") as stderr:
            self.dashboard_process = subprocess.Popen(
                [
                    sys.executable,
                    DASHBOARD_SCRIPT,
                    "--host",
                    DASHBOARD_HOST,
                    "--port",
                    DASHBOARD_PORT,
                ],
                cwd=ROOT_DIR,
                env=self.build_env(),
                stdout=stdout,
                stderr=stderr,
            )

        time.sleep(0.5)
        if self.dashboard_process.poll() is not None:
            self.log("No pude iniciar el dashboard. Revisa data/dashboard.err.")
            self.dashboard_process = None
            return

        self.log(f"Dashboard iniciado en {DASHBOARD_URL}. PID: {self.dashboard_process.pid}")

    def stop_dashboard(self):
        if not self.is_dashboard_running():
            self.dashboard_process = None
            return

        self.log("Apagando dashboard...")
        self.dashboard_process.terminate()
        try:
            self.dashboard_process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.dashboard_process.kill()
            self.dashboard_process.wait(timeout=None)

        self.log("Dashboard apagado.")
        self.dashboard_process = None

    def watch_bot_process(self, process):
        return_code = process.wait()
        with self.lock:
            if self.process is not process:
                return

            self.process = None
            self.log(f"El bot se apago. Codigo de salida: {return_code}")
            self.stop_dashboard()

    def start(self):
        with self.lock:
            if self.is_running():
                self.log("El bot ya esta encendido.")
                self.start_dashboard()
                return

            self.process = subprocess.Popen(
                [sys.executable, BOT_SCRIPT],
                cwd=ROOT_DIR,
                env=self.build_env(),
            )
            self.log(f"Bot iniciado. PID: {self.process.pid}")
            self.start_dashboard()
            threading.Thread(target=self.watch_bot_process, args=(self.process,), daemon=True).start()

    def stop(self):
        with self.lock:
            if not self.is_running():
                self.log("El bot no esta encendido.")
                self.process = None
                self.stop_dashboard()
                return

            process = self.process
            self.log("Apagando bot...")
            process.terminate()
            process.wait(timeout=None)

            if self.process is process:
                self.process = None

            self.log("Bot apagado.")
            self.stop_dashboard()

    def restart(self):
        self.stop()
        self.start()

    def status(self):
        if self.is_running():
            self.log(f"Bot encendido. PID: {self.process.pid}")
        else:
            self.log("Bot apagado.")

        if self.is_dashboard_running():
            self.log(f"Dashboard encendido. PID: {self.dashboard_process.pid} | {DASHBOARD_URL}")
        else:
            self.log("Dashboard apagado.")

    def print_help(self):
        print(
            "\nComandos disponibles:\n"
            "  start    Enciende el bot\n"
            "  stop     Apaga el bot\n"
            "  restart  Reinicia el bot\n"
            "  reset    Reinicia el bot\n"
            "  status   Muestra si el bot esta encendido\n"
            "  help     Muestra esta ayuda\n"
            "  exit     Apaga el bot y cierra esta consola\n",
            flush=True,
        )

    def run(self, autostart=False):
        self.log("Consola lista. Escribe 'help' para ver comandos.")
        if autostart:
            self.start()

        while True:
            try:
                command = input("> ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                command = "exit"

            if command == "start":
                self.start()
            elif command == "stop":
                self.stop()
            elif command in ("restart", "reset"):
                self.restart()
            elif command == "status":
                self.status()
            elif command == "help":
                self.print_help()
            elif command in ("exit", "quit"):
                self.stop()
                self.log("Consola cerrada.")
                break
            elif not command:
                continue
            else:
                self.log(f"Comando desconocido: {command}. Escribe 'help' para ver opciones.")


if __name__ == "__main__":
    BotManager().run(autostart="--start" in sys.argv)
