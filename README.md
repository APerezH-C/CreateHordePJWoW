# CreateHordePJWoW — BotWow

**BotWow keeps trying to create a Horde character on a PvP (JcJ) realm in WoW Forever until it works.**

When a faction is too full, World of Warcraft: Forever refuses new characters with a
"faction imbalance" error. BotWow retries for you, over and over, until the character
is created. Then it stops.

> ⚠️ Unofficial tool. Read the [disclaimer](#disclaimer) before using it.

---

## Contents

1. [What it does](#what-it-does)
2. [What you need](#what-you-need)
3. [Option A: download BotWow.exe (easiest)](#option-a-download-botwowexe-easiest)
4. [Option B: run from source with start.bat](#option-b-run-from-source-with-startbat)
5. [How to use it](#how-to-use-it)
6. [Test mode (--dry-run)](#test-mode---dry-run)
7. [When does it stop?](#when-does-it-stop)
8. [Troubleshooting](#troubleshooting)
9. [Build the exe yourself](#build-the-exe-yourself)
10. [Donations](#donations)
11. [Disclaimer](#disclaimer)

---

## What it does

BotWow looks at the screen and clicks for you, one step at a time:

1. Presses **Jugar** (Play) in Battle.net to start WoW.
2. Chooses the **PvP ruleset (JcJ)**.
3. Chooses **Horde → Troll → Rogue**, **male** body.
4. Types a **random name**.
5. Presses **Terminar** (Finish).
6. If the **faction imbalance error** appears: closes WoW and starts again from step 1.
7. When the character is **created**: stops and leaves WoW open.

There are no fixed timers between screens: every step waits for the right screen.

## What you need

- **Windows 10 or 11.**
- **Battle.net** open and logged in, with **World of Warcraft: Forever** selected
  (the blue **Jugar** button visible).
- WoW client in **Spanish** (the bot reads the Spanish texts on screen).
- A **16:9** screen or window (for example 1920×1080, 2560×1440 or 1600×900).
- **Any** WoW UI scale works.

## Option A: download BotWow.exe (easiest)

1. Open the [**Releases page**](../../releases/latest).
2. Download **BotWow.exe**.
3. Double-click it.

**Windows SmartScreen** may say "Windows protected your PC". The exe is not signed,
so this is normal. Click **More info** → **Run anyway**.

**Antivirus warning?** Tools made with PyInstaller (like this one) are sometimes
flagged by mistake (a false positive). If you prefer not to trust the exe, use
[Option B](#option-b-run-from-source-with-startbat) or
[build it yourself](#build-the-exe-yourself): the full source code is here.

## Option B: run from source with start.bat

1. Install **Python 3.12** from [python.org](https://www.python.org/downloads/).
   In the installer, tick **"Add python.exe to PATH"**.
2. On this page, click **Code → Download ZIP**.
3. **Extract** the ZIP to a folder (do not run it from inside the ZIP).
4. Double-click **start.bat**.

The first time, start.bat installs the only requirement (Pillow). Then it starts the bot.

## How to use it

1. Open Battle.net (logged in, WoW: Forever selected).
2. Start BotWow (BotWow.exe or start.bat).
3. A **support screen** appears. Click **Continue ▶**. The bot starts.
4. Don't use the mouse or keyboard while it runs: the bot needs them.

| Key / action | What it does |
| --- | --- |
| **F9** | Stop at once (works even while WoW has the focus) |
| **F8** | Start again |
| **Close the BotWow window** | Stop and exit |

The main window ("WoW Forever relaunch loop") shows the status, the number of
attempts and the name it will use.

## Test mode (--dry-run)

Test mode does everything **except pressing Terminar**, so no character is created.
Use it to check that the bot works on your PC.

- **Exe:** right-click BotWow.exe → **Create shortcut**. Right-click the shortcut →
  **Properties**. At the end of **Target**, add a space and `--dry-run`, for example:
  `"C:\Games\BotWow\BotWow.exe" --dry-run`. Start BotWow with that shortcut.
- **Source:** open a terminal in the folder and run
  `python loop.py --autostart --dry-run` (or `start.bat --dry-run`).

It stops with "dry run: everything ready, Terminar NOT pressed".

## When does it stop?

**It stops (and beeps) when:**

- After Terminar, the **character list** appears: the character was most likely
  **created**. Check the game.
- After Terminar, nothing happens for 30 seconds.
- After Terminar, an unknown message appears 20 times in a row.

It also stops when you press **F9** (or close the window).

**It closes WoW and tries again when:**

- The faction imbalance error appears (the normal case).
- An unknown message appears after Terminar (for example, the name is taken: it
  picks a new random name).
- A screen stays unknown or stuck for 5 minutes (loading, queue, frozen game).

To close WoW, the bot ends the Wow.exe process.

## Troubleshooting

BotWow writes two things **next to BotWow.exe** (or next to loop.py):

- **loop.log** — what the bot saw and did, step by step.
- **captures/** — a screenshot every time it stops or restarts WoW unexpectedly.

If that folder is read-only, they go to `%LOCALAPPDATA%\BotWow` instead.

| Problem | Try this |
| --- | --- |
| "Battle.net window not found" | Open Battle.net and keep its window open (not only in the tray). |
| "Jugar button is not ready" | Select WoW: Forever in Battle.net and wait for updates to finish. |
| Red warning about the language | Switch the WoW client to Spanish (esES). |
| Red warning about the window size | Use a 16:9 resolution, at least 1600×900. |
| start.bat says Python was not found | Reinstall Python 3.12 and tick "Add python.exe to PATH". |
| It clicks in the wrong place | Check loop.log and captures/, then open an issue with them. |

## Build the exe yourself

1. Install Python 3.12 (see [Option B](#option-b-run-from-source-with-startbat)).
2. Double-click **build.bat**.

It installs the build tools (`requirements-build.txt`: Pillow, PyInstaller) and
creates **dist\BotWow.exe**.

## Donations

BotWow is free. If it saves you time and you want to support it:

- ☕ Ko-fi: https://ko-fi.com/pereziam
- ❤ PayPal: https://paypal.me/pereziam

Optional: the bot works exactly the same without donating.

## Disclaimer

- BotWow is an **unofficial** fan tool. It is **not affiliated with, endorsed or
  supported by Blizzard Entertainment**. World of Warcraft and Battle.net are
  trademarks of Blizzard Entertainment.
- Automating the game **may violate Blizzard's Terms of Service** and **can lead to
  action against your account** (including suspension or ban).
- **Use it at your own risk.** The authors are not responsible for any consequence.
- What BotWow does **not** do:
  - It never asks for or reads your **credentials**.
  - It never reads or changes the game's **memory**.
  - It uses **no network** connection (Ko-fi and PayPal only open in your browser if
    you click them).
- It only looks at the screen, moves the mouse, presses keys and closes Wow.exe. It
  also reads (never writes) WoW's settings file to warn you if the client is not in
  Spanish.
