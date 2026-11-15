# Simple Click2LatLon

Simple Click2LatLon opens websites at the coordinates of a map click in QGIS 4.
Peakfinder is available by default.

## Install and use

Place `simple_click2latlon` in the QGIS profile's `python/plugins` folder or a
directory on `QGIS_PLUGINPATH`. Enable **Simple Click2LatLon** in the QGIS
Plugin Manager.

Choose a website from **Plugins → Simple Click2LatLon**, the shared toolbar
menu, or its dedicated toolbar button. Click the map once to open the website
in your browser. The previous map tool resumes after the click. Press **Esc**
to cancel the selection.

## Manage websites

Open **Plugins → Simple Click2LatLon → Settings…** to add, edit, or delete
websites. Each URL template uses `{lat}` and `{lon}` for WGS 84 latitude and
longitude in decimal degrees. For example,
`https://www.peakfinder.com/?lat={lat}&lng={lon}`.

**Enabled** controls whether the website appears in the plugin menu and
toolbar. **Separate tool** gives an enabled website its own toolbar button.
**Tool with all services** controls the shared toolbar menu for enabled
websites without dedicated buttons.

On save, the plugin copies custom icons into `SimpleClick2LatLon/icons` in
the active QGIS profile and keeps the service definitions in
`SimpleClick2LatLon/services.json`. An empty icon field uses the generic icon.

**Export JSON…** exports the current list of websites and embeds readable
custom icons. **Import JSON…** replaces the list in the settings panel.
Click **OK** to save the imported list.
