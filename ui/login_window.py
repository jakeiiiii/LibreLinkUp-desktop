from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QCheckBox, QMessageBox,
)

from api.client import REGIONS
from utils.version import app_title


class LoginWindow(QWidget):
    login_successful = Signal(dict)  # emits user info dict

    def __init__(self, client, config):
        super().__init__()
        self.client = client
        self.config = config
        self.setWindowTitle(app_title(config, "- Login"))
        self.setFixedSize(380, 340)
        self._build_ui()
        self._load_saved_credentials()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(32, 24, 32, 24)

        # Title
        title = QLabel("LibreLinkUp")
        title.setObjectName("loginTitle")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        layout.addSpacing(8)

        # Region
        region_row = QHBoxLayout()
        region_row.addWidget(QLabel("Region:"))
        self.region_combo = QComboBox()
        self.region_combo.addItems(list(REGIONS.keys()))
        self.region_combo.setCurrentText(self.config.get("region", "Canada"))
        region_row.addWidget(self.region_combo)
        layout.addLayout(region_row)

        # Email
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("Email")
        layout.addWidget(self.email_input)

        # Password
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Password")
        self.password_input.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.password_input)

        # Remember me
        self.remember_cb = QCheckBox("Remember credentials")
        self.remember_cb.setChecked(self.config.get("remember_credentials", False))
        layout.addWidget(self.remember_cb)

        layout.addSpacing(4)

        # Login button
        self.login_btn = QPushButton("Login")
        self.login_btn.setObjectName("loginButton")
        self.login_btn.clicked.connect(self._on_login)
        layout.addWidget(self.login_btn)

        # Status
        self.status_label = QLabel("")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        layout.addStretch()

        # Enter key triggers login
        self.password_input.returnPressed.connect(self._on_login)
        self.email_input.returnPressed.connect(self._on_login)

    def _load_saved_credentials(self):
        if self.config.get("remember_credentials"):
            self.email_input.setText(self.config.get("email", ""))
            self.password_input.setText(self.config.get("password", ""))

    def _on_login(self):
        email = self.email_input.text().strip()
        password = self.password_input.text().strip()
        region = self.region_combo.currentText()

        if not email or not password:
            self.status_label.setText("Please enter email and password.")
            return

        self.login_btn.setEnabled(False)
        self.status_label.setText("Logging in...")
        # Force UI repaint before blocking network call
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()

        try:
            user_info = self.client.login(email, password, region)

            # Save config
            self.config["region"] = region
            self.config["remember_credentials"] = self.remember_cb.isChecked()
            if self.remember_cb.isChecked():
                self.config["email"] = email
                self.config["password"] = password
            else:
                self.config["email"] = ""
                self.config["password"] = ""

            self.login_successful.emit(user_info)

        except Exception as e:
            self.status_label.setText(str(e))
        finally:
            self.login_btn.setEnabled(True)
