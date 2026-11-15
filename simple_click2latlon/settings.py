from dataclasses import replace
from pathlib import Path

from qgis.gui import QgsOptionsPageWidget, QgsOptionsWidgetFactory
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from .services import TITLE, Service, Settings, SettingsStore


class ServiceDialog(QDialog):
    def __init__(self, store: SettingsStore, service: Service, parent=None):
        super().__init__(parent)
        self._store = store
        self._original = service
        self.service = service
        self.setWindowTitle("Edit website" if service.name else "Add website")
        self.setMinimumWidth(530)

        self.name_edit = QLineEdit(service.name, self)
        self.url_edit = QLineEdit(service.url_template, self)
        self.enabled_checkbox = QCheckBox("Enabled", self)
        self.enabled_checkbox.setChecked(service.enabled)
        self.separate_checkbox = QCheckBox("Separate tool", self)
        self.separate_checkbox.setChecked(service.separate_tool)
        self.icon_edit = QLineEdit(store.icon_label(service), self)
        self.icon_edit.setPlaceholderText("Use generic icon")
        browse = QPushButton("Browse…", self)
        browse.clicked.connect(self._browse)
        icon_row = QHBoxLayout()
        icon_row.addWidget(self.icon_edit, 1)
        icon_row.addWidget(browse)
        self.icon_warning = QLabel(self)
        self.icon_warning.setWordWrap(True)
        self.icon_edit.textChanged.connect(self._update_icon_warning)
        self._update_icon_warning()

        url_help = QLabel("Use {lat} and {lon} for the clicked coordinates.", self)
        form = QFormLayout(self)
        form.addRow("Name", self.name_edit)
        form.addRow("URL template", self.url_edit)
        form.addRow("", url_help)
        form.addRow(self.enabled_checkbox)
        form.addRow(self.separate_checkbox)
        form.addRow("Icon file", icon_row)
        form.addRow("", self.icon_warning)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self.name_edit.setFocus()

    def _browse(self) -> None:
        service = self._edited_icon()
        start = str(self._store.icon_path(service.icon)) if service.icon else ""
        filename, _ = QFileDialog.getOpenFileName(self, "Choose a website icon", start)
        if filename:
            self.icon_edit.setText(filename)

    def _edited_icon(self) -> Service:
        icon = self.icon_edit.text().strip()
        if icon == self._store.icon_label(self._original):
            return self._original
        return replace(
            self._original, icon=self._store.icon_reference(icon), icon_data=None
        )

    def _update_icon_warning(self) -> None:
        warning = self._store.icon_warning(self._edited_icon())
        self.icon_warning.setText(warning)
        self.icon_warning.setVisible(bool(warning))

    def accept(self) -> None:
        service = replace(
            self._edited_icon(),
            name=self.name_edit.text().strip(),
            url_template=self.url_edit.text().strip(),
            enabled=self.enabled_checkbox.isChecked(),
            separate_tool=self.separate_checkbox.isChecked(),
        )
        try:
            service.validate()
        except ValueError as error:
            QMessageBox.warning(self, TITLE, str(error))
            return
        self.service = service
        super().accept()


class OptionsPage(QgsOptionsPageWidget):
    def __init__(self, store, settings, save_settings, parent=None):
        super().__init__(parent)
        self._store = store
        self._services = list(settings.services)
        self._save_settings = save_settings

        self.shared_checkbox = QCheckBox("Tool with all services", self)
        self.shared_checkbox.setChecked(settings.tool_with_all_services)
        self.shared_checkbox.setToolTip(
            "Show a toolbar menu for enabled websites without a separate tool."
        )
        self.table = QTableWidget(0, 4, self)
        self.table.setHorizontalHeaderLabels(
            ["Website", "Enabled", "Separate tool", "Icon"]
        )
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        add_button = QPushButton("Add…", self)
        self.edit_button = QPushButton("Edit…", self)
        self.delete_button = QPushButton("Delete", self)
        import_button = QPushButton("Import JSON…", self)
        import_button.setToolTip(
            "Replace the website list with the definitions in a JSON file."
        )
        export_button = QPushButton("Export JSON…", self)
        add_button.clicked.connect(self._add)
        self.edit_button.clicked.connect(self._edit)
        self.delete_button.clicked.connect(self._delete)
        import_button.clicked.connect(self._import)
        export_button.clicked.connect(self._export)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.table.cellDoubleClicked.connect(self._edit)

        buttons = QHBoxLayout()
        for button in (add_button, self.edit_button, self.delete_button):
            buttons.addWidget(button)
        buttons.addStretch()
        buttons.addWidget(import_button)
        buttons.addWidget(export_button)
        layout = QVBoxLayout(self)
        layout.addWidget(self.shared_checkbox)
        layout.addWidget(self.table, 1)
        layout.addLayout(buttons)
        self._populate(0)

    def _populate(self, selected: int) -> None:
        self.table.clearContents()
        self.table.setRowCount(len(self._services))
        for row, service in enumerate(self._services):
            name = QTableWidgetItem(self._store.service_icon(service), service.name)
            name.setToolTip(service.url_template)
            self.table.setItem(row, 0, name)
            self.table.setItem(
                row, 1, QTableWidgetItem("Yes" if service.enabled else "No")
            )
            separate = QTableWidgetItem("Yes" if service.separate_tool else "No")
            self.table.setItem(row, 2, separate)
            warning = self._store.icon_warning(service)
            icon = QTableWidgetItem(self._store.icon_label(service) or "Generic")
            if warning:
                icon.setText(f"⚠ {icon.text()}")
                icon.setToolTip(warning)
            self.table.setItem(row, 3, icon)
        if self._services:
            self.table.selectRow(min(selected, len(self._services) - 1))
        self._update_buttons()

    def _update_buttons(self) -> None:
        selected = bool(self.table.selectedItems())
        self.edit_button.setEnabled(selected)
        self.delete_button.setEnabled(selected)

    def _add(self) -> None:
        dialog = ServiceDialog(self._store, Service("", ""), self)
        if dialog.exec():
            self._services.append(dialog.service)
            self._populate(len(self._services) - 1)

    def _edit(self) -> None:
        row = self.table.currentRow()
        if row >= 0:
            dialog = ServiceDialog(self._store, self._services[row], self)
            if dialog.exec():
                self._services[row] = dialog.service
                self._populate(row)

    def _delete(self) -> None:
        row = self.table.currentRow()
        if row >= 0:
            del self._services[row]
            self._populate(row)

    def _import(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Import websites", "", "JSON (*.json)"
        )
        if filename:
            try:
                services = self._store.import_services(Path(filename))
            except (OSError, ValueError) as error:
                QMessageBox.warning(self, TITLE, f"Could not import websites. {error}")
            else:
                self._services = list(services)
                self._populate(0)

    def _export(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export websites", "click2latlon-services.json", "JSON (*.json)"
        )
        if filename:
            try:
                self._store.export_services(Path(filename), self._services)
            except (OSError, ValueError) as error:
                QMessageBox.warning(self, TITLE, f"Could not export websites. {error}")

    def apply(self) -> None:
        settings = Settings(tuple(self._services), self.shared_checkbox.isChecked())
        try:
            saved = self._save_settings(settings)
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, TITLE, f"Could not save the settings. {error}")
        else:
            self._services = list(saved.services)
            self._populate(max(0, self.table.currentRow()))


class OptionsFactory(QgsOptionsWidgetFactory):
    def __init__(self, plugin, icon):
        super().__init__(TITLE, icon, TITLE)
        self._plugin = plugin

    def createWidget(self, parent=None):
        return OptionsPage(
            self._plugin.store,
            self._plugin.settings,
            self._plugin.save_settings,
            parent,
        )
