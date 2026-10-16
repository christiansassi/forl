<p align="center">
	<img src="assets/banner.png" width="100%" alt="FORL">
	<br><br>
    Made with ❤️ (and a lot of
<img src="assets/ai-llm/claude.svg" alt="Claude" height="16" align="absmiddle">
&nbsp;
<picture>
	<source media="(prefers-color-scheme: dark)" srcset="assets/ai-llm/chatgpt-dark.svg">
	<img src="assets/ai-llm/chatgpt-light.svg" alt="OpenAI" height="16" align="absmiddle">
</picture>
)
<br>
</p>

# Table of Contents

- [Introduction](#introduction)
- [Demo (macOS)](#demo-macos)
- [Installation](#installation)
	- [macOS](#-macos)
	- [Windows](#-windows)
	- [Linux](#-linux)
	- [iOS](#-ios)

# Introduction

This tool helps you keep track of your usage and stay within your limits. It currently supports:

- ChatGPT
- Claude

# Demo (macOS)

<p align="center">
	<img src="assets/demo.gif" width="100%" alt="FORL in the menu bar, the panel, the widgets and Control Center">
</p>

# Installation

## <img src="assets/os/macos.png" alt="macOS" height="24" align="absmiddle"> macOS

> [!IMPORTANT]
> Requires macOS 15 or later and Xcode.

1. Open `src/mac/FORL.xcodeproj` in Xcode.
2. For both the `FORL` and `FORLWidgets` targets, open **Signing & Capabilities**, select your team, and set **Signing Certificate** to **Development**. If Xcode reports that no certificate is available, create one in **Xcode > Settings > Accounts > Manage Certificates** with **+ > Apple Development**.
3. Build and install the app:

	```bash
	bash src/mac/build.command
	```

The app is installed to `/Applications/FORL.app`.

## <img src="assets/os/windows.png" alt="Windows" height="24" align="absmiddle"> Windows

> [!IMPORTANT]
> Requires Python 3.10 or later.

```bash
pip install -r src/windows/requirements.txt
python src/windows/build.py
```

The executable is written to `src/windows/dist/FORL.exe`.

## <img src="assets/os/linux.png" alt="Linux" height="24" align="absmiddle"> Linux

> [!IMPORTANT]
> Requires Python 3.10 or later with Tk.

```bash
pip install -r src/linux/requirements.txt
python3 src/linux/build.py
```

The executable is written to `src/linux/dist/FORL`.

| Distribution (default desktop) | Tray icons | Panel and settings | Start at login | Status bar | Desktop widget |
|---|:-:|:-:|:-:|:-:|:-:|
| Ubuntu (GNOME) | ✅ | ✅ | ✅ | ✅\*\*\* | ✅\*\*\*\* |
| Fedora Workstation (GNOME) | ✅\* | ✅ | ✅ | ✅\*\*\* | ✅\*\*\*\* |
| Debian (GNOME) | ✅\* | ✅ | ✅ | ✅\*\*\* | ✅\*\*\*\* |
| Linux Mint (Cinnamon) | ✅ | ✅ | ✅ | ✅\*\*\* | ❌ |
| Arch Linux (none) | ✅\*\* | ✅ | ✅ | ✅\*\*\* | ✅\*\* |
| Manjaro (KDE Plasma) | ✅ | ✅ | ✅ | ✅\*\*\* | ✅ |
| openSUSE Tumbleweed (KDE Plasma) | ✅ | ✅ | ✅ | ✅\*\*\* | ✅ |
| Pop!_OS (COSMIC) | ✅ | ✅ | ✅ | ✅\*\*\* | ❌ |

\* Needs the [AppIndicator and KStatusNotifierItem Support](https://extensions.gnome.org/extension/615/appindicator-support/) GNOME extension, which Ubuntu ships turned on. Without a tray, FORL opens its panel as an ordinary window, and closing it quits.<br><br>
\*\* Depends on the desktop you install: the tray works on KDE Plasma, Cinnamon, XFCE, MATE, Budgie, COSMIC and in Waybar, and on GNOME with the extension above; the desktop widget needs KDE Plasma 6, or GNOME 45 or later.<br><br>
\*\*\* Needs a bar that shows a command's output, such as Waybar, Polybar or i3blocks, or on GNOME FORL's own extension (see below) or one such as [Executor](https://extensions.gnome.org/extension/2932/executor/).<br><br>
\*\*\*\* On GNOME the widget is an extension that puts FORL's tray icons in the top bar and opens the same panel, and needs GNOME 45 or later. Where FORL already has tray icons, as on Ubuntu, it stays hidden so the readings are not shown twice.

### Status bar

FORL writes each service's reading to `~/.cache/forl/claude.json` and `~/.cache/forl/chatgpt.json` in Waybar's format, and as plain text in `claude.txt` and `chatgpt.txt`: point a custom module of your bar at them.

### Desktop widget

On KDE Plasma 6, FORL installs its widget when it starts: add it from **Add Widgets**.

### GNOME extension

On GNOME 45 or later, FORL installs its extension when it starts but does not turn it on: turn it on in the **Extensions** app, or with

```bash
gnome-extensions enable usage@forl.io
```

On Wayland, GNOME Shell only sees a newly installed extension after you log out and back in.

The extension and FORL talk over the session bus: the readings reach the top bar as soon as FORL takes them, the extension tells you when FORL is not running, and signing in or the settings open FORL's own panel, starting FORL first when it is closed. While the extension is on, FORL opens its panel from the top bar as it would from a tray.

## <img src="assets/os/macos.png" alt="iOS" height="24" align="absmiddle"> iOS

> [!IMPORTANT]
> Requires the [Scriptable](https://apps.apple.com/app/scriptable/id1405459188) app.

1. Copy `src/ios/FORL.js` into the Scriptable folder in iCloud Drive, or paste it into a new script.
2. Run it in Scriptable to sign in.
3. Add a Scriptable widget to the home screen or the lock screen, and choose FORL as its script.

A widget shows the current session, and the week where it has room. To choose what it shows, run FORL, tap **Usages**, tick them in order, tap **Copy the Parameter**, and paste it into the widget's **Parameter** in **Edit Widget**: the small and lock screen widgets show the first usage, the medium one the first one's service, the large one every service. The background, black or white, is set in the same place.
