from base64 import b64decode, b64encode
from dataclasses import dataclass, replace
import json
from os.path import expanduser
from pathlib import Path

from qgis.PyQt.QtCore import QIODevice, QSaveFile, QUrl
from qgis.PyQt.QtGui import QIcon, QImageReader, QPixmap

TITLE = "Simple Click2LatLon"
ICONS = Path(__file__).with_name("icons")
BUNDLED_PEAKFINDER = "builtin:peakfinder"


@dataclass(frozen=True)
class Service:
    name: str
    url_template: str
    enabled: bool = True
    separate_tool: bool = False
    icon: str = ""
    icon_data: bytes | None = None

    def url(self, lat: float, lon: float) -> QUrl:
        url = self.url_template.replace("{lat}", f"{lat:.8f}")
        url = url.replace("{lon}", f"{lon:.8f}")
        return QUrl(url, QUrl.ParsingMode.StrictMode)

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("Enter a website name.")
        if "{lat}" not in self.url_template or "{lon}" not in self.url_template:
            raise ValueError("The URL template must contain both {lat} and {lon}.")
        url = self.url(0, 0)
        if not url.isValid() or url.scheme() not in ("https", "http") or not url.host():
            raise ValueError("Enter a valid HTTP or HTTPS URL template.")


@dataclass(frozen=True)
class Settings:
    services: tuple[Service, ...] = (
        Service(
            "Peakfinder",
            "https://www.peakfinder.com/?lat={lat}&lng={lon}&fov=110",
            icon=BUNDLED_PEAKFINDER,
        ),
    )
    tool_with_all_services: bool = True


def _encode_service(service: Service) -> dict:
    return {
        "name": service.name,
        "url_template": service.url_template,
        "enabled": service.enabled,
        "separate_tool": service.separate_tool,
        "icon": service.icon,
    }


def _decode_services(
    document: object, *, importing: bool = False
) -> tuple[Service, ...]:
    if not isinstance(document, dict) or not isinstance(document.get("services"), list):
        raise ValueError('Expected a JSON object with a "services" list.')
    services = []
    for index, item in enumerate(document["services"], start=1):
        try:
            if not isinstance(item, dict):
                raise ValueError("Expected a website definition.")
            definition = _encode_service(Service("", ""))
            for key, default in definition.items():
                value = item.get(key, default)
                if not isinstance(value, type(default)):
                    raise ValueError(f"Invalid {key} value.")
                definition[key] = value.strip() if isinstance(value, str) else value
            service = Service(**definition)
            service.validate()
            if importing and "icon_data" in item:
                payload = item["icon_data"]
                if not isinstance(payload, str) or not service.icon:
                    raise ValueError("Expected image data and an icon filename.")
                data = b64decode(payload, validate=True)
                if not QPixmap().loadFromData(data):
                    raise ValueError("The embedded icon could not be read.")
                service = replace(service, icon_data=data)
        except ValueError as error:
            raise ValueError(f"Website {index}. {error}") from error
        services.append(service)
    return tuple(services)


def _write_json(path: Path, document: dict) -> None:
    data = (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    file = QSaveFile(str(path))
    if not file.open(QIODevice.OpenModeFlag.WriteOnly):
        raise OSError(file.errorString())
    if file.write(data) != len(data):
        file.cancelWriting()
        raise OSError(file.errorString())
    if not file.commit():
        raise OSError(file.errorString())


class SettingsStore:
    def __init__(self, directory: Path):
        self.path = directory / "services.json"
        self.icon_dir = directory / "icons"

    def load(self) -> Settings:
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return Settings()
        services = _decode_services(document)
        shared_tool = document.get("tool_with_all_services", True)
        if not isinstance(shared_tool, bool):
            raise ValueError("Invalid shared toolbar setting.")
        return Settings(services, shared_tool)

    def save(
        self, settings: Settings, previous: Settings
    ) -> tuple[Settings, list[str]]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        created = []
        services = []
        try:
            for service in settings.services:
                service.validate()
                services.append(self._save_icon(service, created))
            _write_json(
                self.path,
                {
                    "tool_with_all_services": settings.tool_with_all_services,
                    "services": [_encode_service(service) for service in services],
                },
            )
        except (OSError, ValueError):
            self._remove_icons(created)
            raise

        old_names = {
            self._owned_filename(service.icon) for service in previous.services
        }
        new_names = {self._owned_filename(service.icon) for service in services}
        warnings = self._remove_icons(
            self.icon_dir / name for name in old_names - new_names if name is not None
        )
        return replace(settings, services=tuple(services)), warnings

    def import_services(self, path: Path) -> tuple[Service, ...]:
        return _decode_services(
            json.loads(path.read_text(encoding="utf-8")), importing=True
        )

    def export_services(self, path: Path, services: list[Service]) -> None:
        if path.resolve() == self.path.resolve():
            raise ValueError("Choose a file outside the plugin settings.")
        definitions = []
        for service in services:
            definition = _encode_service(service)
            if service.icon and service.icon != BUNDLED_PEAKFINDER:
                source = self.icon_path(service.icon)
                data = service.icon_data
                if data is None and QImageReader(str(source)).canRead():
                    data = source.read_bytes()
                if data is not None:
                    definition["icon"] = source.name
                    definition["icon_data"] = b64encode(data).decode("ascii")
            definitions.append(definition)
        _write_json(path, {"services": definitions})

    @staticmethod
    def _owned_filename(icon: str) -> str | None:
        path = Path(icon)
        if path.parent == Path("icons") and path.name != "..":
            return path.name
        return None

    def icon_path(self, icon: str) -> Path:
        if icon == BUNDLED_PEAKFINDER:
            return ICONS / "peakfinder.svg"
        if name := self._owned_filename(icon):
            return self.icon_dir / name
        return Path(expanduser(icon))

    def icon_reference(self, text: str) -> str:
        if not text:
            return ""
        path = Path(expanduser(text))
        if path.name == text and (self.icon_dir / path).is_file():
            return f"icons/{path.name}"
        path = path.absolute()
        if path.parent == self.icon_dir.absolute() and path.name != "..":
            return f"icons/{path.name}"
        return str(path)

    def icon_label(self, service: Service) -> str:
        if service.icon == BUNDLED_PEAKFINDER:
            return "peakfinder.svg"
        return self._owned_filename(service.icon) or service.icon

    def icon_warning(self, service: Service) -> str:
        if not service.icon or service.icon_data is not None:
            return ""
        path = self.icon_path(service.icon)
        if not path.is_file():
            return "Icon file does not exist. The generic icon will be used."
        if not QImageReader(str(path)).canRead():
            return "Icon file could not be read. The generic icon will be used."
        return ""

    def service_icon(self, service: Service) -> QIcon:
        if service.icon_data is not None:
            pixmap = QPixmap()
            if pixmap.loadFromData(service.icon_data):
                return QIcon(pixmap)
        if service.icon and not self.icon_warning(service):
            return QIcon(str(self.icon_path(service.icon)))
        return QIcon(str(ICONS / "service.svg"))

    def _save_icon(self, service: Service, created: list[Path]) -> Service:
        data = service.icon_data
        if data is None:
            if (
                not service.icon
                or service.icon == BUNDLED_PEAKFINDER
                or self._owned_filename(service.icon)
                or self.icon_warning(service)
            ):
                return service
            data = self.icon_path(service.icon).read_bytes()

        name = Path(service.icon).name
        if name in ("", ".", ".."):
            raise ValueError("Enter an icon filename.")
        filename = Path(name)
        self.icon_dir.mkdir(exist_ok=True)
        destination = self.icon_dir / filename
        suffix = 2
        while True:
            try:
                output = destination.open("xb")
            except FileExistsError:
                destination = (
                    self.icon_dir / f"{filename.stem}-{suffix}{filename.suffix}"
                )
                suffix += 1
            else:
                created.append(destination)
                with output:
                    output.write(data)
                return replace(
                    service, icon=f"icons/{destination.name}", icon_data=None
                )

    @staticmethod
    def _remove_icons(paths) -> list[str]:
        warnings = []
        for path in paths:
            try:
                path.unlink(missing_ok=True)
            except OSError as error:
                warnings.append(str(error))
        return warnings
