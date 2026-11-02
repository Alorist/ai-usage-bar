# AI Usage Bar

A small bar on your Windows taskbar that shows how much of your **Claude** and **Codex** subscription limits you've used, plus what your token usage would have cost at API prices.

![AI Usage Bar on the taskbar](docs/screenshot.png)

```
● Claude 5h ━── 24%  wk ━── 18% │ ● Codex 5h ─── 0%  wk ─── 0% │ 1d $52.56  7d $410
```

- **Claude** (Pro / Max): 5-hour session and weekly limits, the same numbers as Claude Code's `/usage`.
- **Codex** (ChatGPT Plus / Pro): 5-hour and weekly limits, from your Codex CLI history.
- **Tokens** (optional): today's and this week's usage at API prices, via [ccusage](https://github.com/ryoppippi/ccusage).
- **Hover** any section for reset times and details. Bars turn amber at 70% and red at 90%.
- It hides itself while a game or video is fullscreen. Sections for tools you don't use are left out.

## Install

1. Install [Rainmeter](https://www.rainmeter.net/) 4.5 or newer (or run `winget install Rainmeter.Rainmeter`).
2. Download `AIUsageBar_x.y.z.rmskin` from [Releases](../../releases) and double-click it.
3. Click **Install**. The bar appears on your taskbar within a few seconds.

You need to be signed in to **Claude Code** with a Claude subscription and/or to the **Codex CLI** with ChatGPT. The bar uses those existing logins; there's nothing to configure.

**Optional, for the 1d / 7d cost figures:** install [Node.js](https://nodejs.org/) and run `npm i -g ccusage`.

### Using it

Right-click the bar for:
- **Refresh usage now**
- **Show as desktop bar instead**: moves it to a pill at the top centre of your screen.
- **Open data folder**

To remove it, right-click → Rainmeter → Unload skin, or delete `Documents\Rainmeter\Skins\AIUsageBar`.

## How it works

The skin runs `aiusage.exe` (bundled, about 9 MB, no Python needed) every 5 minutes and redraws every 30 seconds.

| Section | Source |
|---|---|
| Claude | One HTTPS request to `api.anthropic.com/api/oauth/usage`, using the login Claude Code keeps in `%USERPROFILE%\.claude\.credentials.json` |
| Codex | The most recent `rate_limits` entry in `%USERPROFILE%\.codex\sessions\` (only updates when you use Codex) |
| Tokens | `ccusage daily --json`, if installed |

`CLAUDE_CONFIG_DIR` and `CODEX_HOME` are respected if you've moved those folders.

A second, long-running `aiusage.exe helper` process keeps the bar parked left of the system tray, and hides it while a window is fullscreen on your main monitor. It exits when Rainmeter closes.

## Privacy and security

- **Nothing leaves your PC except one request to Anthropic,** carrying your own Claude Code login token. There's no telemetry, no other servers, and no auto-updates.
- **The token is never stored or logged.** It's read from Claude Code's file each time and sent only to `api.anthropic.com`.
- **It never refreshes or changes your Claude login.** If the login has expired, the Claude section shows "offline" until you next open Claude Code.
- **ccusage is never downloaded automatically.** It's only used if you installed it yourself.
- **Your usage numbers stay local,** in `Documents\Rainmeter\Skins\AIUsageBar\@Resources\data\`.

> **Heads-up:** the Claude usage endpoint is the one Claude Code itself uses for `/usage`, but it isn't a documented public API. It could change or stop working without notice. If it does, the Claude section shows "offline" and the rest keeps working.

`aiusage.exe` is built with PyInstaller from [`src/aiusage.py`](src/aiusage.py). Some antivirus tools are suspicious of unsigned PyInstaller programs. You can read the source and build it yourself (below).

## Build from source

Needs Python 3.12+ on the build machine:

```powershell
.\build.ps1 -Version 1.0.0
```

This creates a build virtualenv, bundles `src\aiusage.py` with PyInstaller (pinned in `requirements-build.txt`), regenerates the skin layouts with `tools\gen_skins.py`, and writes `dist\AIUsageBar_1.0.0.rmskin`.

| Path | What |
|---|---|
| `src/aiusage.py` | Data fetching (`collect`) and taskbar placement / fullscreen hiding (`helper`) |
| `skin/AIUsageBar/@Resources/AIUsage.lua` | Turns the data into what the bar shows, plus tooltips |
| `tools/gen_skins.py` | Generates `Taskbar.ini` and `Mini.ini` |
| `tools/make_rmskin.py` | Packs the `.rmskin` (leaves out runtime data and logs) |

## Troubleshooting

- **A section says offline:** check `@Resources\data\aiusage.log` (right-click → Open data folder).
- **The Claude section is missing:** Claude Code isn't signed in with a subscription on this PC.
- **The Codex section is missing:** there's no `~\.codex\sessions` folder yet. Use Codex once.
- **The bar sits in the wrong place:** it parks left of the tray on a bottom taskbar. With the taskbar on the side or top, it goes to the bottom-right of the desktop instead.

## License

MIT. See [LICENSE](LICENSE). Not affiliated with Anthropic or OpenAI.
