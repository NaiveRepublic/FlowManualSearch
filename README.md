# Flow Manual Search

An offline search window for the **Dirac Flow 5.6 user manual**. Type a question in your own words and it shows which section and page of the manual covers it, with a preview of the page and the spot marked.

The finished program is a single file, `FlowManualSearch.exe`, for Windows 11 and later. It never connects to the internet: the manual, the search index and the language model are all inside the file.

## Using the program

1. Double-click `FlowManualSearch.exe`.
2. Type a question, for example *How do I connect Flow to the device?*, and press Enter.
3. Each result shows the section number, title, chapter, page and the matching text.
4. Click a title or **Show on page** to see the page inside the window, with the section marked in blue. Use the arrows to turn pages.
5. Click **Open PDF at page …** to open the real manual in Microsoft Edge at that page.

Shortcuts: `/` jumps to the search box, `Esc` closes the page preview, and the left and right arrow keys turn pages. Click the title in the top left to go back to the start screen with the chapter list.

## Building the .exe (one time)

The package you downloaded contains everything needed to produce the .exe. Pick **one** of these three routes.

### Route A: build it yourself on a Windows PC (simplest)

1. Install **Python 3.12** from <https://www.python.org/downloads/windows/>. In the installer, tick **Add python.exe to PATH**.
2. Unzip this package to a folder, for example `C:\FlowManualSearch`.
3. Double-click **`build.bat`**. The first run downloads the build tools and takes a few minutes.
4. When it finishes, a folder opens with **`FlowManualSearch.exe`**. That file is all you need to share.

The computers that *run* the .exe need nothing installed: no Python and no internet.

### Route B: let Claude Code build it on your Windows PC

1. Install Claude Code for desktop from <https://claude.ai/download>.
2. Unzip this package and open the folder in Claude Code.
3. Ask: *"Build FlowManualSearch.exe and test it."*

The file `CLAUDE.md` in this folder tells Claude Code how the project works. It will ask for your approval before installing anything.

### Route C: build it in the cloud with GitHub

1. Create a **private** repository on GitHub. Private matters, because the repository will contain the Dirac manual.
2. Upload the contents of this folder, including the hidden `.github` folder.
3. Open the **Actions** tab. The build "Build Windows exe" starts by itself (or click **Run workflow**).
4. When it shows a green tick, open the run and download **FlowManualSearch** under *Artifacts*. It is a zip containing the .exe.

## When a new manual version arrives

Drag the new manual PDF onto **`build.bat`**. It rebuilds the search index from the new PDF, runs a quality check, and packages a new .exe.

The quality check (`build_tools/eval_queries.py`) asks 25 test questions and reports how many find the right section. The section numbers in that test are from version 5.6. If chapters are renumbered, update the expected numbers in that file. The search itself works either way.

## Teaching it new words

The program understands everyday phrasing through a meaning-based model, and a small synonym list helps where people's words differ from the manual's. For example, "repeat" also finds "loop", and "copy" also finds "duplicate".

To add your own, copy `app/synonyms.json`, edit it, and place it **next to `FlowManualSearch.exe`**. The program uses that file instead of the built-in one, so no rebuild is needed. Each line maps one everyday word to the manual's words:

```json
"repeat": ["loop"],
```

## Troubleshooting

**"Windows protected your PC" appears on first start.** The .exe is not code-signed, so Windows SmartScreen does not recognise it yet. Click **More info**, then **Run anyway**. For wide distribution inside a company, IT can sign the .exe with the company certificate.

**Antivirus quarantines the file.** Single-file programs packaged this way are sometimes flagged by mistake. Ask IT to allow it, or build it yourself with Route A, so the file comes from your own machine.

**The window does not open.** The program logs problems to `%LOCALAPPDATA%\FlowManualSearch\log.txt`. If the built-in Windows window component (WebView2) fails, the program automatically opens the same interface in Microsoft Edge instead, served only on this computer (127.0.0.1).

**Startup takes a couple of seconds.** That is normal for a single-file program: it unpacks itself on each start.

## What is inside

| Part | Purpose |
|---|---|
| `app/main.py` | Starts the window and connects it to the search |
| `app/search_engine.py` | Ranks manual passages by meaning and by keywords |
| `app/ui/index.html` | The search window |
| `app/data/` | The prepared index, page previews and the manual |
| `app/synonyms.json` | Everyday words mapped to the manual's vocabulary |
| `build_tools/build_index.py` | Reads a manual PDF and builds `app/data/` |
| `build_tools/eval_queries.py` | Quality check with 25 test questions |
| `manual/` | The source PDF used to build the current index |
| `build.bat` | One-click build on Windows |
| `FlowManualSearch.spec` | Packaging recipe used by `build.bat` |
| `.github/workflows/` | Cloud build recipe for Route C |

**How the search works.** At build time, the manual is split into its 172 numbered sections and 200 short passages. Each passage is turned into a vector of numbers that captures its meaning, using the WordLlama model (16 MB, MIT licence). At search time, your question goes through the same process, and passages are ranked by a blend of meaning similarity and keyword overlap. Everything runs locally in a fraction of a millisecond.

**Licences of components inside the .exe.** NumPy (BSD), Hugging Face tokenizers (Apache 2.0), pywebview (BSD), pythonnet (MIT) and the WordLlama model weights (MIT). PyMuPDF is used only by `build_index.py` to read the PDF at build time and is not included in the .exe.
