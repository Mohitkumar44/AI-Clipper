"""Placeholder settings dialog for future desktop configuration controls."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout, QWidget


class SettingsDialog(QDialog):
    """Present a non-persistent placeholder for future application settings."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create the placeholder without reading or persisting configuration.

        Args:
            parent: Optional owning Qt widget.
        """
        super().__init__(parent)
        self.setWindowTitle("Settings")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Settings will be available in a future release.", self))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
