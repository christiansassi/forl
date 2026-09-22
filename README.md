<p align="center">
	<img src="assets/banner.png" width="100%" alt="FORL">
	<br><br>
    Made with ❤️ (and a lot of
<img src="assets/claude.svg" alt="Claude" height="16" align="absmiddle">
&nbsp;
<picture>
	<source media="(prefers-color-scheme: dark)" srcset="assets/chatgpt-dark.svg">
	<img src="assets/chatgpt-light.svg" alt="OpenAI" height="16" align="absmiddle">
</picture>
)
<br>
</p>

# Table of Contents

- [Introduction](#introduction)
- [Demo](#demo)
- [Installation](#installation)
	- [Windows](#windows)
	- [macOS](#macos)

# Introduction

This tool helps you keep track of your usage and stay within your limits. It currently supports:

- ChatGPT
- Claude

# Demo

<p align="center">
	<img src="assets/demo.gif" width="100%" alt="FORL in the menu bar, the panel, the widgets and Control Center">
</p>

# Installation

## Windows

> [!IMPORTANT]
> Requires Python 3.10 or later.

```bash
pip install -r src/windows/requirements.txt
python src/windows/build.py
```

The executable is written to `src/windows/dist/FORL.exe`.

## macOS

> [!IMPORTANT]
> Requires macOS 15 or later and Xcode.

1. Open `src/mac/FORL.xcodeproj`src/mac/FORL.xcodeproj in Xcode.
2. For both the `FORL` and `FORLWidgets` targets, select your team under **Signing & Capabilities**.
3. Build and install the app:

	```bash
	bash src/mac/build.command
	```

The app is installed to `/Applications/FORL.app`.
