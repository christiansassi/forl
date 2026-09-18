<p align="center">
	<img src="assets/banner.png" width="100%" alt="">
    Made with ❤️ (and a lot of
<img src="assets/icons/claude.svg" alt="Claude" height="16" align="absmiddle">
&nbsp;
<picture>
	<source media="(prefers-color-scheme: dark)" srcset="assets/icons/chatgpt-dark.svg">
	<img src="assets/icons/chatgpt-light.svg" alt="OpenAI" height="16" align="absmiddle">
</picture>
)
</p>

On Windows, install Python 3.10 or newer. From the repository root, install
dependencies once with `python -m pip install -r src/windows/requirements.txt`,
then run `python src/windows/build.py` using the same Python environment.
The builder creates `src/windows/dist/FORL.exe`, including Python and the
required assets. It does not install dependencies or create an environment.
Run `FORL.exe --claude` or `FORL.exe --chatgpt`, or create shortcuts with those
arguments. Keep the executable in its permanent location before enabling startup.
After replacing an older Python launch, switch startup off and on to update it.

Each Windows usage icon has a persistent identity of its own. Drag individual
icons between the visible notification area and the `^` overflow menu, including
different metrics for the same provider. Arrange them once after updating to
this version. Keep `FORL.exe` at the same path so Windows can retain those
preferences across restarts and rebuilds.

On macOS 15 or newer, install and open Xcode to finish its setup, then run
`bash src/mac/build.command`. The helper builds the Release app and its widget
extension, verifies the signature, and installs `FORL.app` into `~/Applications`,
replacing an existing copy. Quit FORL before reinstalling, then open the installed
app from Finder. macOS uses Swift and needs no Python dependencies.
