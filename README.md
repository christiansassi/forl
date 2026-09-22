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
2. For both the `FORL` and `FORLWidgets` targets, select your team under **Signing & Capabilities**.
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

TBA
