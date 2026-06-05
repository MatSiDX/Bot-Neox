from datetime import datetime


def log_event(message):
    timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)
