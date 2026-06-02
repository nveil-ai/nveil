# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Clément Baraille
# SPDX-License-Identifier: AGPL-3.0-or-later

import os
import sys
import threading
import time
from datetime import datetime

import psutil


def start_resource_metrics_logger(service="UNKNOWN", interval=1):
    def worker():
        while True:
            log_resource_metrics(service)
            time.sleep(interval)
    t = threading.Thread(target=worker, daemon=True)
    t.start()

def log_resource_metrics(service="UNKNOWN"):
    proc = psutil.Process(os.getpid())
    cpu = proc.cpu_percent(interval=1)
    cpu_normalized = cpu / psutil.cpu_count()
    mem = proc.memory_percent()
    msg = f"CPU={cpu_normalized:.1f}%, MEM={mem:.1f}%"
    logger(service=service).log("METRIC", msg, suppress_console=True)

def _is_gcp():
    return os.environ.get("GCP", "0") == "1"

class LogLevel:
    DEFAULT = "DEFAULT"
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    SUCCESS = "SUCCESS"

LOG_COLORS = {
    LogLevel.DEFAULT: "\033[0m",
    LogLevel.DEBUG: "\033[33m",        # Yellow
    LogLevel.INFO: "\033[97m",         # White (bright)
    LogLevel.WARNING: "\033[38;5;208m",# Orange
    LogLevel.ERROR: "\033[91m",        # Red (bright)
    LogLevel.SUCCESS: "\033[32m",      # Green
}

SERVICE_COLORS = {
    "SERVER": "\033[35m",
    "AI": "\033[34m",
    "VIZ": "\033[33m",
}

def _logfmt_line(service, level, msg, extra_labels=None):
    labels = {
        "service": service or "UNKNOWN",
        "level": level,
    }
    if extra_labels:
        labels.update(extra_labels)
    label_str = " ".join(f'{k}="{v}"' for k, v in labels.items())
    return f'{label_str} msg="{msg}"'

class logger:
    _instance = None
    _lock = threading.Lock()
    _start_time = time.time()
    _service = None
    _service_id = None
    _file_handle = None  # ajout
    _log_file_path = "/workspaces/app/nveil/backend/log_service/app.log"

    def __new__(cls, service=None, service_id=None, log_file_path=None):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(logger, cls).__new__(cls)
                    cls._service = service
                    cls._service_id = service_id
        elif service is not None:
            cls._service = service
        if service_id is not None:
            cls._service_id = service_id
        if log_file_path:
            cls._log_file_path = log_file_path
        # ouverture fichier (line buffered) si disponible
        try:
            if cls._file_handle is None:
                log_dir = os.path.dirname(cls._log_file_path)
                if log_dir and not os.path.exists(log_dir):
                    os.makedirs(log_dir, exist_ok=True)
                cls._file_handle = open(cls._log_file_path, "a", buffering=1)
        except Exception:
            cls._file_handle = None
        return cls._instance

    def _format_msg(self, level, msg):
        if _is_gcp():
            return self._format_msg_gcp(level, msg)
        # now = datetime.now().strftime("%y-%m-%d %H:%M:%S")
        now = datetime.now().strftime("%H:%M:%S")
        elapsed = time.time() - self._start_time
        color = LOG_COLORS.get(level, LOG_COLORS[LogLevel.DEFAULT])
        reset = LOG_COLORS[LogLevel.DEFAULT]
        service_id_tag = f"[{self._service_id}]" if self._service_id is not None else ""
        if self._service and self._service in SERVICE_COLORS:
            service_tag = f"{SERVICE_COLORS[self._service]}[{self._service}]{reset}"
        elif self._service:
            # service_tag = f"[{self._service}]{service_id_tag}"
            service_tag = f"[{self._service}]"
        else:
            service_tag = ""
        # Re-apply color after every newline so multi-line messages stay colored
        msg = msg.replace("\n", f"{reset}\n{color}")
        # return f"{service_tag}[{now}] (+{elapsed:.2f}s) {color}[{level}] {msg}{reset}"
        return f"{color}[{level}] {msg}{reset}"

    def _format_msg_gcp(self, level, msg):
        """Compact, no-color, single-line format for GCP Cloud Logging.
        GCP adds its own timestamp so we skip date/time.
        Newlines are replaced to prevent log entry splitting."""
        msg = msg.replace("\n", " | ")
        service_id_tag = f"[{self._service_id}]" if self._service_id is not None else ""
        service_tag = f"[{self._service.strip()}]" if self._service else ""
        return f"{service_tag}{service_id_tag}[{level}] {msg}"

    def log(self, level, *args, suppress_console=False):
        msg = " ".join(str(a) for a in args)
        formatted = self._format_msg(level, msg)
        # flush seulement pour ERROR
        if not suppress_console:
            print(
                formatted,
                file=sys.stderr if level == LogLevel.ERROR else sys.stdout,
                flush=(level == LogLevel.ERROR)
            )
        # écriture fichier (tamponnée) pour conservation
        if self._file_handle:
            try:
                self._file_handle.write(formatted + "\n")
            except Exception:
                pass

    def logp(self, level, *args):
        self.log(level, *args)

    def debug(self, *args, suppress_console=False):
        self.log(LogLevel.DEBUG, *args, suppress_console=suppress_console)

    def info(self, *args, suppress_console=False):
        self.log(LogLevel.INFO, *args, suppress_console=suppress_console)

    def warning(self, *args, suppress_console=False):
        self.log(LogLevel.WARNING, *args, suppress_console=suppress_console)

    def error(self, *args, suppress_console=False):
        self.log(LogLevel.ERROR, *args, suppress_console=suppress_console)

    def success(self, *args, suppress_console=False):
        self.log(LogLevel.SUCCESS, *args, suppress_console=suppress_console)

    def default(self, *args, suppress_console=False):
        self.log(LogLevel.DEFAULT, *args, suppress_console=suppress_console)

def log(level, *args):
    logger().log(level, *args)

def logp(level, *args):
    logger().logp(level, *args)

INFO = LogLevel.INFO
DEBUG = LogLevel.DEBUG
WARNING = LogLevel.WARNING
ERROR = LogLevel.ERROR
SUCCESS = LogLevel.SUCCESS
DEFAULT = LogLevel.DEFAULT

# Usage example:
# from tools.logger import logger, log, logp, LogLevel
# logger = logger(service="SERVER")
# logger.info("App started")
# log(INFO, "This is a warning")
# logp(ERROR, "This is an error")

# import threading
# import time
# from datetime import datetime
# import sys

# class LogLevel:
#     DEFAULT = "DEFAULT"
#     DEBUG = "DEBUG"
#     INFO = "INFO"
#     WARNING = "WARNING"
#     ERROR = "ERROR"
#     SUCCESS = "SUCCESS"

# # ANSI color codes for each log level
# LOG_COLORS = {
#     LogLevel.DEFAULT: "\033[0m",
#     LogLevel.DEBUG: "\033[36m",    # Cyan
#     LogLevel.INFO: "\033[32m",     # Green
#     LogLevel.WARNING: "\033[33m",  # Yellow
#     LogLevel.ERROR: "\033[31m",    # Red
#     LogLevel.SUCCESS: "\033[92m",  # Bright Green
# }

# # Service-specific colors
# SERVICE_COLORS = {
#     "SERVER": "\033[35m",      # Magenta
#     "  AI  ": "\033[34m",  # Blue
#     "VIZ SV": "\033[33m",      # Yellow
#     # Add more as needed
# }

# class logger:
#     _instance = None
#     _lock = threading.Lock()
#     _start_time = time.time()
#     _service = None
#     _service_id = None

#     def __new__(cls, service=None, service_id=None):
#         if not cls._instance:
#             with cls._lock:
#                 if not cls._instance:
#                     cls._instance = super(logger, cls).__new__(cls)
#                     cls._service = service
#                     cls._service_id = service_id
#         elif service is not None:
#             cls._service = service
#         if service_id is not None:
#             cls._service_id = service_id
#         return cls._instance

#     def _format_msg(self, level, msg):
#         now = datetime.now().strftime("%y-%m-%d %H:%M:%S")
#         elapsed = time.time() - self._start_time
#         color = LOG_COLORS.get(level, LOG_COLORS[LogLevel.DEFAULT])
#         reset = LOG_COLORS[LogLevel.DEFAULT]
#         # Color the service tag if a color is defined
#         service_id_tag = ""
#         if self._service_id is not None:
#             service_id_tag = f"[{self._service_id}]"
#         if self._service and self._service in SERVICE_COLORS:
#             service_tag = f"{SERVICE_COLORS[self._service]}[{self._service}]{service_id_tag}{reset}"
#         elif self._service:
#             service_tag = f"[{self._service}]{service_tag}"
#         else:
#             service_tag = ""
#         return f"{service_tag}[{now}] (+{elapsed:.2f}s) {color}[{level}] {msg}{reset}"

#     def log(self, level, *args):
#         msg = " ".join(str(a) for a in args)
#         print(self._format_msg(level, msg), file=sys.stderr if level == LogLevel.ERROR else sys.stdout, flush=True)

#     def logp(self, level, *args):
#         self.log(level, *args)

#     def debug(self, *args):
#         self.log(LogLevel.DEBUG, *args)

#     def info(self, *args):
#         self.log(LogLevel.INFO, *args)

#     def warning(self, *args):
#         self.log(LogLevel.WARNING, *args)

#     def error(self, *args):
#         self.log(LogLevel.ERROR, *args)

#     def success(self, *args):
#         self.log(LogLevel.SUCCESS, *args)

#     def default(self, *args):
#         self.log(LogLevel.DEFAULT, *args)

# # Free functions for convenience, similar to C++ bindings
# def log(level, *args):
#     logger().log(level, *args)

# def logp(level, *args):
#     logger().logp(level, *args)

# INFO = LogLevel.INFO
# DEBUG = LogLevel.DEBUG
# WARNING = LogLevel.WARNING
# ERROR = LogLevel.ERROR
# SUCCESS = LogLevel.SUCCESS
# DEFAULT = LogLevel.DEFAULT

# # Usage example:
# # from tools.logger import logger, log, logp, LogLevel
# # logger = logger(service="SERVER")
# # logger.info("App started")
# # log(INFO, "This is a warning")
# # logp(ERROR, "This is an error")