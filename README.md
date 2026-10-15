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
| Ubuntu (GNOME) | ✅ | ✅ | ✅ | ✅\*\*\* | ❌ |
| Fedora Workstation (GNOME) | ✅\* | ✅ | ✅ | ✅\*\*\* | ❌ |
| Debian (GNOME) | ✅\* | ✅ | ✅ | ✅\*\*\* | ❌ |
| Linux Mint (Cinnamon) | ✅ | ✅ | ✅ | ✅\*\*\* | ❌ |
| Arch Linux (none) | ✅\*\* | ✅ | ✅ | ✅\*\*\* | ✅\*\* |
| Manjaro (KDE Plasma) | ✅ | ✅ | ✅ | ✅\*\*\* | ✅ |
| openSUSE Tumbleweed (KDE Plasma) | ✅ | ✅ | ✅ | ✅\*\*\* | ✅ |
| Pop!_OS (COSMIC) | ✅ | ✅ | ✅ | ✅\*\*\* | ❌ |

\* Needs the [AppIndicator and KStatusNotifierItem Support](https://extensions.gnome.org/extension/615/appindicator-support/) GNOME extension, which Ubuntu ships turned on. Without a tray, FORL opens its panel as an ordinary window, and closing it quits.<br><br>
\*\* Depends on the desktop you install: the tray works on KDE Plasma, Cinnamon, XFCE, MATE, Budgie, COSMIC and in Waybar, and on GNOME with the extension above; the desktop widget needs KDE Plasma 6.<br><br>
\*\*\* Needs a bar that shows a command's output, such as Waybar, Polybar or i3blocks, or on GNOME an extension such as [Executor](https://extensions.gnome.org/extension/2932/executor/).

### Status bar

FORL writes each service's reading to `~/.cache/forl/claude.json` and `~/.cache/forl/chatgpt.json` in Waybar's format, and as plain text in `claude.txt` and `chatgpt.txt`: point a custom module of your bar at them.

### Desktop widget

On KDE Plasma 6, FORL installs its widget when it starts: add it from **Add Widgets**.
