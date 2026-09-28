# 🎮 Cs-1.6-Tournament-Hud

### CS 1.6 Esports Tournament Stream HUD & Match Control Center

A modern, frame-accurate tournament stream overlay and centralized match control center designed for **Counter-Strike 1.6** broadcasting with **OBS Studio** and **AMX Mod X**.

---

## ✨ Features

- **🏆 Dynamic Tournament Overlay**:
  - Top scoreboard with team names, scores, and round status.
  - **Frame-Accurate Clock Synchronization**: Engine-level precision with `get_gametime()` matching the in-game HUD exactly across freeze time, live rounds, and bomb plant states.
  - **Authentic CS 1.6 C4 Sprite**: Clean C4 icon badge with live countdown when the bomb is planted.
  - **Real-Time Player Cards**: Left and right side panels showing player nicknames, alive/dead state, HP bar, armor, current active weapons, defuse kits, and C4 bomb carrier badge.
- **🖥️ 1-Click Stream & Match Control Center (`config_app.py`)**:
  - Live server monitor and match status detection.
  - 1-Click HLDS server launcher (auto-port discovery, customizable maps).
  - 1-Click game client launcher and automated server connection.
  - Match controls: **Start Match** (`mr15 cal`), **Force LIVE** (`/start`), and **Stop Match**.
  - Tournament map switcher (`de_dust2`, `de_inferno`, `de_nuke`).
  - Friendly fire toggle (syncs live via RCON and updates server configs).
  - Instant team name and color customization with live preview.
  - Automatic screenshot organizer: routes all end-round snapshots directly to `Screenshots/`.
- **🔌 Native AMX Mod X Plugin (`cs_stream_hud.sma`)**:
  - Zero third-party dependencies.
  - High-frequency 100ms non-blocking live state exporter.

---

## 📁 Repository Structure

```
├── .env.example                                      # Environment variables template
├── .gitignore                                        # Security & binary filter
├── cstrike/
│   ├── obs_overlay/                                  # Stream Overlay Web Assets & Control GUI
│   │   ├── tournament_overlay.html                   # Main 1080p tournament stream HUD
│   │   ├── cs_sprites.js                             # Base64 fallback sprite library
│   │   ├── sprites/                                  # CS 1.6 weapon/bomb/item sprites
│   │   ├── config_app.py                             # Match & Stream Control Center application
│   │   ├── Open Config.bat                           # 1-Click Control Center launcher
│   │   ├── overlay_config.txt                        # Saved team and color configs
│   │   ├── live_overlay.html                         # Compact scoreboard overlay fallback
│   │   └── player_hud.html                           # Standalone player HUD fallback
│   └── addons/
│       └── amxmodx/
│           ├── scripting/
│           │   └── cs_stream_hud.sma                 # AMX Mod X HUD exporter source code
│           ├── plugins/
│           │   └── cs_stream_hud.amxx                # Compiled binary plugin
│           └── configs/
│               └── amxmd/                            # AMX Match Deluxe league configs
```

---

## 🚀 Quick Start Guide

### 1. Requirements
- Counter-Strike 1.6 with Metamod & AMX Mod X 1.8.2+.
- Python 3.8+ (for running the Control Center application).
- OBS Studio (for capturing the HTML browser source).

### 2. Launch the Control Center
Double-click [`cstrike/obs_overlay/Open Config.bat`](file:///d:/Counter-Strike%20WaRzOnE/cstrike/obs_overlay/Open%20Config.bat) or run:
```bash
python cstrike/obs_overlay/config_app.py
```

### 3. Setup in OBS Studio
1. Open **OBS Studio**.
2. Under **Sources**, click **+** and choose **Browser**.
3. Check **Local file** and browse to:
   ```
   cstrike/obs_overlay/tournament_overlay.html
   ```
4. Set dimensions to:
   - **Width**: `1920`
   - **Height**: `1080`
5. Check **Refresh browser when scene becomes active**.

---

## 🔒 Security & Privacy

This repository includes a strict [`.gitignore`](file:///d:/Counter-Strike%20WaRzOnE/.gitignore) to ensure no sensitive files or proprietary binaries are committed:
- **Crash Dumps**: Memory minidumps (`*.mdmp`) are strictly ignored.
- **Server Logs**: Match connection history, client IP addresses, and RCON logs (`*.log`) are ignored.
- **Personal Game Files**: Private `config.cfg`, `userconfig.cfg`, and admin lists (`users.ini`) are excluded.
- **Game Assets**: Proprietary Valve engine binaries (`*.dll`, `*.exe`, `valve/`, `*.bsp`) are excluded.

---

## 📄 License
This project is open-source and licensed under the [MIT License](LICENSE).
