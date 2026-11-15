from math import isfinite
from pathlib import Path

from qgis.core import (
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsCsException,
)
from qgis.gui import QgsMapTool
from qgis.PyQt import sip
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QAction, QCursor, QDesktopServices, QIcon
from qgis.PyQt.QtWidgets import QApplication, QMenu, QToolButton

from .services import ICONS, TITLE, Service, Settings, SettingsStore
from .settings import OptionsFactory


class ClickMapTool(QgsMapTool):
    def __init__(self, canvas, clicked, canceled):
        super().__init__(canvas)
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
        self._clicked = clicked
        self._canceled = canceled
        self._press = None

    def canvasPressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press = event.pos()

    def canvasReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            press, self._press = self._press, None
            if (
                press is not None
                and (event.pos() - press).manhattanLength()
                < QApplication.startDragDistance()
            ):
                self._clicked(event.originalMapPoint())

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            event.accept()
            self._canceled()
        else:
            super().keyPressEvent(event)

    def deactivate(self) -> None:
        self._press = None
        super().deactivate()


class SimpleClick2LatLonPlugin:
    def __init__(self, iface):
        self.iface = iface
        self._canvas = iface.mapCanvas()
        self.store = SettingsStore(
            Path(QgsApplication.qgisSettingsDirPath()) / "SimpleClick2LatLon"
        )
        self.settings = Settings()
        self._selected_index: int | None = None
        self._previous_tool = None
        self._tool = ClickMapTool(self._canvas, self._open_service, self._restore_tool)
        self._service_actions: list[QAction] = []
        self._separate_actions: dict[int, QAction] = {}
        self._shared_action = None
        self._shared_button = None

    def initGui(self) -> None:
        try:
            self.settings = self.store.load()
        except (OSError, ValueError) as error:
            self.iface.messageBar().pushWarning(
                TITLE, f"Could not load settings. {error}"
            )

        self._options_factory = OptionsFactory(
            self, QIcon(str(ICONS / "simple-click2latlon.svg"))
        )
        self.iface.registerOptionsWidgetFactory(self._options_factory)

        self._settings_action = QAction(
            QgsApplication.getThemeIcon("/mActionOptions.svg"),
            "Settings…",
            self.iface.mainWindow(),
        )
        self._settings_action.triggered.connect(self._open_settings)
        self._canvas.mapToolSet.connect(self._map_tool_changed)
        self._build_actions()

    def unload(self) -> None:
        self._restore_tool()
        self._canvas.mapToolSet.disconnect(self._map_tool_changed)
        self._remove_actions()
        self._settings_action.deleteLater()
        self.iface.unregisterOptionsWidgetFactory(self._options_factory)
        self._options_factory.deleteLater()
        self._tool.deleteLater()

    def _open_settings(self) -> None:
        self.iface.showOptionsDialog(self.iface.mainWindow(), TITLE)

    def save_settings(self, settings: Settings) -> Settings:
        settings, warnings = self.store.save(settings, self.settings)
        if settings != self.settings:
            self._restore_tool()
            self._remove_actions()
            self.settings = settings
            self._build_actions()
        for warning in warnings:
            self.iface.messageBar().pushWarning(
                TITLE, f"Could not remove an old icon. {warning}"
            )
        return settings

    def _build_actions(self) -> None:
        window = self.iface.mainWindow()
        shared_menu = None
        if self.settings.tool_with_all_services:
            button = QToolButton()
            button.setIcon(QIcon(str(ICONS / "all-services.svg")))
            button.setText("Tool with all services")
            button.setAccessibleName("Simple Click2LatLon websites")
            button.setCheckable(True)
            button.setAutoRaise(True)
            button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            shared_menu = QMenu(button)
            button.setMenu(shared_menu)
            self._shared_button = button
            self._shared_action = self.iface.addToolBarWidget(button)

        for index, service in enumerate(self.settings.services):
            if not service.enabled:
                continue
            icon = self.store.service_icon(service)
            title = service.name.replace("&", "&&")
            action = QAction(icon, title, window)
            action.setCheckable(True)
            action.setData(index)
            action.triggered.connect(lambda _checked, index=index: self._arm(index))
            self.iface.addPluginToMenu(TITLE, action)
            self._service_actions.append(action)

            if service.separate_tool:
                separate_action = QAction(icon, title, window)
                separate_action.setCheckable(True)
                separate_action.setToolTip(f"Open {service.name} at the next map click")
                separate_action.triggered.connect(
                    lambda _checked, index=index: self._arm(index)
                )
                self.iface.addToolBarIcon(separate_action)
                self._separate_actions[index] = separate_action
            elif shared_menu is not None:
                shared_menu.addAction(action)

        if shared_menu is not None:
            self._shared_button.setEnabled(not shared_menu.isEmpty())
        self.iface.addPluginToMenu(TITLE, self._settings_action)
        self._sync_actions()

    def _remove_actions(self) -> None:
        if self._shared_action is not None:
            self.iface.removeToolBarIcon(self._shared_action)
            self._shared_action.deleteLater()
            self._shared_action = self._shared_button = None
        for action in self._separate_actions.values():
            self.iface.removeToolBarIcon(action)
            action.deleteLater()
        self._separate_actions.clear()
        for action in self._service_actions:
            self.iface.removePluginMenu(TITLE, action)
            action.deleteLater()
        self._service_actions.clear()
        self.iface.removePluginMenu(TITLE, self._settings_action)

    def _arm(self, index: int) -> None:
        current = self._canvas.mapTool()
        self._selected_index = index
        if current is not self._tool:
            self._previous_tool = current
            self._canvas.setMapTool(self._tool)
        self._sync_actions()

    def _sync_actions(self) -> None:
        selected = self._selected_index
        for action in self._service_actions:
            action.setChecked(action.data() == selected)
        for index, action in self._separate_actions.items():
            action.setChecked(index == selected)
        if self._shared_button is not None:
            active = selected is not None and selected not in self._separate_actions
            self._shared_button.setChecked(active)
            tooltip = "Choose a website to open at the next map click"
            if active:
                name = self.settings.services[selected].name
                tooltip = f"Open {name} at the next map click"
            self._shared_button.setToolTip(tooltip)

    def _map_tool_changed(self, tool, _old_tool) -> None:
        if tool is not self._tool:
            self._selected_index = self._previous_tool = None
            self._sync_actions()

    def _restore_tool(self) -> None:
        previous = self._previous_tool
        self._selected_index = self._previous_tool = None
        if self._canvas.mapTool() is self._tool:
            if previous is not None and not sip.isdeleted(previous):
                self._canvas.setMapTool(previous)
            else:
                self._canvas.unsetMapTool(self._tool)
        self._sync_actions()

    def _open_service(self, point) -> None:
        if self._selected_index is None:
            return
        service: Service = self.settings.services[self._selected_index]
        map_settings = self._canvas.mapSettings()
        source = map_settings.destinationCrs()
        context = map_settings.transformContext()
        self._restore_tool()

        if not source.isValid():
            self.iface.messageBar().pushWarning(
                TITLE, "The map has no valid coordinate reference system."
            )
            return

        try:
            transform = QgsCoordinateTransform(
                source, QgsCoordinateReferenceSystem("EPSG:4326"), context
            )
            coordinates = transform.transform(point)
        except QgsCsException as error:
            self.iface.messageBar().pushWarning(
                TITLE, f"Could not transform the map coordinates. {error}"
            )
            return
        lat, lon = coordinates.y(), coordinates.x()
        if not isfinite(lat) or not isfinite(lon):
            self.iface.messageBar().pushWarning(
                TITLE, "The click did not produce valid coordinates."
            )
            return

        url = service.url(lat, lon)
        if not url.isValid() or not QDesktopServices.openUrl(url):
            self.iface.messageBar().pushWarning(
                TITLE, f"Could not open {service.name} in the browser."
            )
