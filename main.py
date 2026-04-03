import ctypes
import sys
import logging
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QFile

# ── Single instance check (Windows named mutex) ──
_mutex = ctypes.windll.kernel32.CreateMutexW(None, True, "LibreLinkUp.Desktop.SingleInstance")
if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
    sys.exit(0)

# Tell Windows this is its own app so it gets its own taskbar icon
# (without this, python.exe's icon is used and setWindowIcon is ignored)
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("LibreLinkUp.Desktop.1")
except Exception:
    pass

from api.client import LibreLinkUpClient
from ui.login_window import LoginWindow
from ui.main_window import MainWindow
from utils.config import load_config, save_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


class App:
    def __init__(self):
        self.qapp = QApplication(sys.argv)
        self._load_stylesheet()

        self.config = load_config()
        self.client = LibreLinkUpClient()

        self.login_window = LoginWindow(self.client, self.config)
        self.login_window.login_successful.connect(self._on_login_success)

        self.main_window = None

    def _load_stylesheet(self):
        # Try multiple paths for the stylesheet (dev vs packaged)
        candidates = [
            Path(__file__).parent / "resources" / "style.qss",
            Path(sys._MEIPASS) / "resources" / "style.qss" if hasattr(sys, "_MEIPASS") else None,
        ]
        for path in candidates:
            if path and path.exists():
                qfile = QFile(str(path))
                if qfile.open(QFile.ReadOnly):
                    self.qapp.setStyleSheet(qfile.readAll().data().decode())
                    qfile.close()
                    return

    def _on_login_success(self, user_info):
        save_config(self.config)
        self.login_window.hide()

        self.main_window = MainWindow(self.client, self.config)
        self.main_window.logout_requested.connect(self._on_logout)
        self.main_window.show()
        self.main_window.start()

    def _on_logout(self):
        if self.main_window:
            self.main_window.stop_timer()
            self.main_window.close()
            self.main_window = None

        self.client = LibreLinkUpClient()
        self.login_window = LoginWindow(self.client, self.config)
        self.login_window.login_successful.connect(self._on_login_success)
        self.login_window.show()

    def run(self) -> int:
        if self._try_auto_login():
            return self.qapp.exec()

        self.login_window.show()
        return self.qapp.exec()

    def _try_auto_login(self) -> bool:
        """Attempt login with saved credentials. Returns True if successful."""
        if not self.config.get("remember_credentials"):
            return False
        email = self.config.get("email", "").strip()
        password = self.config.get("password", "").strip()
        region = self.config.get("region", "Canada")
        if not email or not password:
            return False
        try:
            user_info = self.client.login(email, password, region)
            self._on_login_success(user_info)
            return True
        except Exception:
            return False


def main():
    app = App()
    sys.exit(app.run())


if __name__ == "__main__":
    main()
