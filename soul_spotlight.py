#!/usr/bin/env python3
import os
import sys
import glob
import signal
import configparser
import subprocess
import urllib.parse
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib

PID_FILE = f"/tmp/soul-search-{os.getuid()}.pid"

CSS = b"""
window {
    background-color: #1e1e2e;
    border: 1px solid #45475a;
    border-radius: 12px;
}
entry {
    background-color: #313244;
    color: #cdd6f4;
    border: none;
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 16px;
}
list {
    background-color: transparent;
}
row {
    border-radius: 8px;
    padding: 4px 8px;
    color: #cdd6f4;
}
row:selected {
    background-color: #45475a;
    color: #ffffff;
}
"""

class SoulSearchWindow(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.set_title("Soul Search")
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_skip_taskbar_hint(True)
        self.set_keep_above(True)
        self.set_position(Gtk.WindowPosition.CENTER_ALWAYS)
        self.set_default_size(580, 380)

        style_provider = Gtk.CssProvider()
        style_provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            style_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        vbox.set_margin_start(14)
        vbox.set_margin_end(14)
        vbox.set_margin_top(14)
        vbox.set_margin_bottom(14)
        self.add(vbox)

        self.entry = Gtk.SearchEntry()
        self.entry.set_placeholder_text("Search apps, math (=), or Google...")
        self.entry.connect("search-changed", self.on_search_changed)
        self.entry.connect("activate", self.on_activate_item)
        vbox.pack_start(self.entry, False, False, 0)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_min_content_height(300)
        vbox.pack_start(scrolled, True, True, 0)

        self.listbox = Gtk.ListBox()
        self.listbox.connect("row-activated", self.on_row_activated)
        scrolled.add(self.listbox)

        self.apps = self.load_applications()
        self.update_results("")

        self.connect("key-press-event", self.on_key_press)
        self.connect("focus-out-event", lambda w, e: self.hide_launcher())

    def load_applications(self):
        apps = []
        paths = [
            "/usr/share/applications/*.desktop",
            os.path.expanduser("~/.local/share/applications/*.desktop")
        ]
        seen = set()
        for pattern in paths:
            for file_path in glob.glob(pattern):
                config = configparser.ConfigParser(interpolation=None)
                try:
                    config.read(file_path, encoding="utf-8")
                    if "Desktop Entry" not in config:
                        continue
                    entry = config["Desktop Entry"]
                    if entry.get("NoDisplay", "false").lower() == "true":
                        continue
                    if entry.get("Hidden", "false").lower() == "true":
                        continue
                    name = entry.get("Name", "").strip()
                    exec_cmd = entry.get("Exec", "").strip()
                    icon = entry.get("Icon", "application-x-executable").strip()
                    if name and exec_cmd and name not in seen:
                        seen.add(name)
                        apps.append({"name": name, "exec": exec_cmd, "icon": icon})
                except Exception:
                    continue
        return sorted(apps, key=lambda x: x["name"].lower())

    def update_results(self, query):
        for child in self.listbox.get_children():
            self.listbox.remove(child)

        query = query.strip()
        matches = []

        if query.startswith("="):
            expr = query[1:].strip()
            allowed = set("0123456789+-*/().% ")
            if expr and all(c in allowed for c in expr):
                try:
                    result = eval(expr, {"__builtins__": None}, {})
                    matches.append({
                        "name": f"= {result}",
                        "exec": "",
                        "icon": "accessories-calculator"
                    })
                except Exception:
                    pass
        else:
            q_lower = query.lower()
            if q_lower:
                starts = [a for a in self.apps if a["name"].lower().startswith(q_lower)]
                contains = [a for a in self.apps if q_lower in a["name"].lower() and a not in starts]
                matches = starts + contains
            else:
                matches = self.apps[:8]

        if query and not query.startswith("="):
            encoded_q = urllib.parse.quote(query)
            matches.append({
                "name": f"Search Google for '{query}'",
                "exec": f"google-chrome https://www.google.com/search?q={encoded_q}",
                "icon": "web-browser"
            })

        for item in matches[:8]:
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            box.set_margin_top(6)
            box.set_margin_bottom(6)
            box.set_margin_start(6)
            box.set_margin_end(6)

            image = Gtk.Image.new_from_icon_name(item["icon"], Gtk.IconSize.DND)
            image.set_pixel_size(24)
            box.pack_start(image, False, False, 0)

            label = Gtk.Label(label=item["name"], xalign=0)
            box.pack_start(label, True, True, 0)

            row.add(box)
            row.app_data = item
            self.listbox.add(row)

        self.listbox.show_all()
        children = self.listbox.get_children()
        if children:
            self.listbox.select_row(children[0])

    def on_search_changed(self, entry):
        self.update_results(entry.get_text())

    def on_row_activated(self, listbox, row):
        if hasattr(row, "app_data") and row.app_data["exec"]:
            exec_str = row.app_data["exec"]
            if exec_str.startswith("google-chrome"):
                subprocess.Popen(exec_str.split(), start_new_session=True)
            else:
                cmd_parts = [p for p in exec_str.split() if not p.startswith("%")]
                if cmd_parts:
                    subprocess.Popen(cmd_parts, start_new_session=True)
        self.hide_launcher()

    def on_activate_item(self, entry):
        selected = self.listbox.get_selected_row()
        if selected:
            self.on_row_activated(self.listbox, selected)

    def on_key_press(self, widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self.hide_launcher()
            return True
        elif event.keyval in (Gdk.KEY_Down, Gdk.KEY_Up):
            children = self.listbox.get_children()
            if not children:
                return True
            selected = self.listbox.get_selected_row()
            idx = children.index(selected) if selected in children else 0
            if event.keyval == Gdk.KEY_Down:
                idx = (idx + 1) % len(children)
            else:
                idx = (idx - 1) % len(children)
            self.listbox.select_row(children[idx])
            return True
        return False

    def hide_launcher(self):
        self.hide()
        self.entry.set_text("")

    def toggle_window(self):
        if self.get_visible():
            self.hide_launcher()
        else:
            self.show_all()
            self.present()
            self.entry.grab_focus()
        return GLib.SOURCE_CONTINUE

def signal_running_instance():
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                pid = int(f.read().strip())
            os.kill(pid, signal.SIGUSR1)
            return True
        except (ProcessLookupError, ValueError, OSError):
            os.remove(PID_FILE)
    return False

def main():
    is_toggle = "--toggle" in sys.argv
    if signal_running_instance():
        sys.exit(0)

    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    win = SoulSearchWindow()
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR1, win.toggle_window)

    if is_toggle:
        win.toggle_window()

    try:
        Gtk.main()
    finally:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)

if __name__ == "__main__":
    main()