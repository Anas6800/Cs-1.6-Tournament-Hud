#!/usr/bin/env python3
"""
CS 1.6 Centralized Overlay & Match Control Center
-------------------------------------------------
All-in-one GUI for:
1. Team names & color customization with live preview
2. Instant file updates (overlay_config.txt, live_overlay.html, live_scores.txt, score.txt)
3. 1-Click HLDS Server Launcher (Port 27016, de_dust2, 10 maxplayers, VAC Off)
4. 1-Click Game Launcher (via CS16Launcher with auto-connect to server)
5. Real-Time Match Controller (Start Match, Force LIVE, Stop Match via RCON)
6. Live Server & Match Status Monitor
"""

import os
import re
import sys
import time
import shutil
import socket
import subprocess
import webbrowser
import ctypes
import tkinter as tk
from tkinter import ttk, colorchooser, messagebox

# Paths
OVERLAY_DIR = os.path.dirname(os.path.abspath(__file__))
CSTRIKE_DIR = os.path.dirname(OVERLAY_DIR)
BASE_DIR = os.path.dirname(CSTRIKE_DIR)
SCREENSHOTS_DIR = os.path.join(BASE_DIR, "Screenshots")
if not os.path.exists(SCREENSHOTS_DIR):
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

CONFIG_PATH = os.path.join(OVERLAY_DIR, "overlay_config.txt")
LIVE_SCORES_PATH = os.path.join(OVERLAY_DIR, "live_scores.txt")
SCORE_TXT_PATH = os.path.join(OVERLAY_DIR, "score.txt")
LIVE_DATA_JS_PATH = os.path.join(OVERLAY_DIR, "live_data.js")
LIVE_OVERLAY_HTML_PATH = os.path.join(OVERLAY_DIR, "live_overlay.html")
TOURNAMENT_OVERLAY_HTML_PATH = os.path.join(OVERLAY_DIR, "tournament_overlay.html")
PLAYER_HUD_HTML_PATH = os.path.join(OVERLAY_DIR, "player_hud.html")

HLDS_EXE = os.path.join(BASE_DIR, "hlds.exe")
CS_LAUNCHER = os.path.join(BASE_DIR, "CS16Launcher.exe")
HL_EXE = os.path.join(BASE_DIR, "hl.exe")
AUTOEXEC_PATH = os.path.join(CSTRIKE_DIR, "autoexec.cfg")
USERCONFIG_PATH = os.path.join(CSTRIKE_DIR, "userconfig.cfg")

SERVER_IP = os.getenv("CS_SERVER_IP", "127.0.0.1")
# Dedicated Server candidate ports - starts at 27016 so 27015 & 27005 are reserved for the game client
DEFAULT_PORTS = [27016, 27017, 27018, 27019, 27020]
CURRENT_PORT = 27016
RCON_PASS = os.getenv("CS_RCON_PASSWORD", "123")
MAP_NAME = os.getenv("CS_MAP_NAME", "de_dust2")
MAX_PLAYERS = int(os.getenv("CS_MAX_PLAYERS", "12"))
HOSTNAME = os.getenv("CS_HOSTNAME", "CS WaRzOnE Server")


def is_hlds_on_port(port):
    """Pings port to see if our HLDS GoldSource server is running on it"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(0.3)
    try:
        sock.sendto(b"\xFF\xFF\xFF\xFFTSource Engine Query\0", (SERVER_IP, port))
        data, _ = sock.recvfrom(1024)
        return len(data) > 0
    except Exception:
        return False
    finally:
        sock.close()


def find_active_hlds_port():
    """Scans candidate ports to detect an already running HLDS server"""
    global CURRENT_PORT
    if is_hlds_on_port(CURRENT_PORT):
        return CURRENT_PORT
    for p in DEFAULT_PORTS:
        if p != CURRENT_PORT and is_hlds_on_port(p):
            CURRENT_PORT = p
            return p
    return None


def is_udp_port_available(port):
    """Checks if a UDP port is free to bind (not taken by another process)"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind((SERVER_IP, port))
        sock.close()
        return True
    except OSError:
        return False


def get_available_port(preferred_port=27016):
    """Finds first available port: checks preferred, then scans candidates"""
    if is_udp_port_available(preferred_port):
        return preferred_port
    for p in DEFAULT_PORTS:
        if p != preferred_port and is_udp_port_available(p):
            return p
    return preferred_port


def is_hlds_online():
    """Returns True if HLDS server is active on any supported port"""
    return find_active_hlds_port() is not None


def get_server_port():
    """Returns the currently active HLDS port if online, or best available port for launch"""
    active = find_active_hlds_port()
    if active:
        return active
    return get_available_port(CURRENT_PORT)


def send_rcon_cmd(command, port=None):
    """Sends GoldSource RCON UDP command to HLDS on the active port"""
    target_port = port or find_active_hlds_port() or CURRENT_PORT
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(1.5)
    try:
        sock.sendto(b"\xFF\xFF\xFF\xFFchallenge rcon\n", (SERVER_IP, target_port))
        data, _ = sock.recvfrom(4096)
        parts = data.decode("latin1", errors="ignore").replace("\x00", "").strip().split()
        if not parts:
            return False, "No challenge response from server"
        challenge = parts[-1]

        rcon_packet = f'\xFF\xFF\xFF\xFFrcon {challenge} {RCON_PASS} {command}\n'.encode("latin1")
        sock.sendto(rcon_packet, (SERVER_IP, target_port))
        data, _ = sock.recvfrom(4096)
        cleaned = data.decode("latin1", errors="ignore").replace("\xFF\xFF\xFF\xFFl", "").replace("\x00", "").strip()
        return True, cleaned
    except Exception as e:
        return False, str(e)
    finally:
        sock.close()


def get_hl_client_pids():
    """Returns list of PIDs belonging strictly to hl.exe (game client, never hlds.exe)"""
    pids = []
    try:
        no_window_flag = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        out = subprocess.check_output(
            ["tasklist", "/FI", "IMAGENAME eq hl.exe", "/FO", "CSV", "/NH"],
            creationflags=no_window_flag
        ).decode("latin1", errors="ignore")
        for line in out.strip().splitlines():
            parts = [p.strip(' "') for p in line.split(',')]
            if len(parts) >= 2 and parts[0].lower() == "hl.exe":
                try:
                    pids.append(int(parts[1]))
                except ValueError:
                    pass
    except Exception:
        pass
    return pids


def find_hl_client_window():
    """Finds the main window belonging strictly to hl.exe"""
    hl_pids = get_hl_client_pids()
    if not hl_pids:
        return None
    found_hwnd = None

    def enum_cb(hwnd, _):
        nonlocal found_hwnd
        if ctypes.windll.user32.IsWindowVisible(hwnd):
            pid = ctypes.c_ulong()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value in hl_pids:
                found_hwnd = hwnd
                return False
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    ctypes.windll.user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
    return found_hwnd


def send_key(vk, scan_code=0):
    user32 = ctypes.windll.user32
    if not scan_code:
        scan_code = user32.MapVirtualKeyW(vk, 0)
    user32.keybd_event(vk, scan_code, 0, 0)
    time.sleep(0.04)
    user32.keybd_event(vk, scan_code, 2, 0)  # KEYEVENTF_KEYUP
    time.sleep(0.04)


def send_paste():
    user32 = ctypes.windll.user32
    VK_CONTROL = 0x11
    VK_V = 0x56
    ctrl_scan = user32.MapVirtualKeyW(VK_CONTROL, 0)
    v_scan = user32.MapVirtualKeyW(VK_V, 0)
    user32.keybd_event(VK_CONTROL, ctrl_scan, 0, 0)
    time.sleep(0.04)
    user32.keybd_event(VK_V, v_scan, 0, 0)
    time.sleep(0.04)
    user32.keybd_event(VK_V, v_scan, 2, 0)
    user32.keybd_event(VK_CONTROL, ctrl_scan, 2, 0)
    time.sleep(0.04)


class CSControlCenter:
    def __init__(self, root):
        self.root = root
        self.root.title("🎮 CS 1.6 Stream & Match Control Center")
        self.root.geometry("720x920")
        self.root.configure(bg="#121824")
        self.root.minsize(680, 800)

        # File paths
        self.config_path = CONFIG_PATH

        # Default colors
        self.colors = {
            "team1": "#00ff41",
            "team2": "#ff4757",
            "status": "#ffaa00",
            "border": "#00ff41"
        }

        # Team names
        self.team_names = {
            "team1": tk.StringVar(value="Aimbots"),
            "team2": tk.StringVar(value="Deadshot")
        }

        # Selected Map (de_dust2, de_inferno, de_nuke)
        self.selected_map = tk.StringVar(value="de_dust2")
        self.map_buttons = {}

        # Friendly Fire (0 = OFF, 1 = ON)
        self.friendly_fire = tk.IntVar(value=self.get_current_friendly_fire())

        self.setup_styles()
        self.create_widgets()
        self.load_config()
        self.update_preview()

        # Start periodic status updates
        self.poll_status()

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")

        style.configure("Title.TLabel",
                        background="#121824",
                        foreground="#00ff41",
                        font=("Segoe UI", 16, "bold"))

        style.configure("Dark.TLabel",
                        background="#0f1419",
                        foreground="white",
                        font=("Segoe UI", 10))

        style.configure("Dark.TEntry",
                        fieldbackground="#1e293b",
                        background="#1e293b",
                        foreground="white",
                        bordercolor="#334155")

    def create_widgets(self):
        # Create canvas with scrollbar for clean display on all screens
        container = tk.Frame(self.root, bg="#121824")
        container.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(container, bg="#121824", highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        self.scroll_frame = tk.Frame(self.canvas, bg="#121824", padx=20, pady=15)

        self.scroll_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw", width=680)
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Mousewheel binding
        self.canvas.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        # 1. Header Title
        title_frame = tk.Frame(self.scroll_frame, bg="#121824")
        title_frame.pack(fill=tk.X, pady=(0, 15))

        title_lbl = tk.Label(title_frame, text="🎮 CS 1.6 Match & Stream Control Center",
                             bg="#121824", fg="#00ff41", font=("Segoe UI", 16, "bold"))
        title_lbl.pack()

        subtitle_lbl = tk.Label(title_frame, text="Configure Teams, Launch Server, & Control Live Matches in One Click",
                                bg="#121824", fg="#64748b", font=("Segoe UI", 9))
        subtitle_lbl.pack()

        # 2. Server & Match Live Status Banner
        self.create_status_banner(self.scroll_frame)

        # 3. 🚀 ONE-CLICK SERVER & MATCH CONTROLS (Top Priority!)
        self.create_controls_section(self.scroll_frame)

        # 4. 🗺️ Map Selector (de_dust2, de_inferno, de_nuke)
        self.create_map_section(self.scroll_frame)

        # 5. 🛡️ Server Rules & Friendly Fire Toggle
        self.create_rules_section(self.scroll_frame)

        # 6. Team Names Section
        self.create_team_section(self.scroll_frame)

        # 5. Colors Section
        self.create_colors_section(self.scroll_frame)

        # 6. Live Preview Section
        self.create_preview_section(self.scroll_frame)

        # 7. Action Buttons (Save & Reset)
        self.create_buttons_section(self.scroll_frame)

    def create_status_banner(self, parent):
        banner_frame = tk.Frame(parent, bg="#0a0f18", relief=tk.RIDGE, bd=1, padx=12, pady=10)
        banner_frame.pack(fill=tk.X, pady=(0, 15))

        self.server_status_lbl = tk.Label(banner_frame, text="🖥️ HLDS Server: Checking...",
                                          bg="#0a0f18", fg="#94a3b8", font=("Segoe UI", 10, "bold"))
        self.server_status_lbl.pack(anchor=tk.W)

        self.match_status_lbl = tk.Label(banner_frame, text="⚔️ Match State: WAITING (0 - 0)",
                                         bg="#0a0f18", fg="#38bdf8", font=("Segoe UI", 10))
        self.match_status_lbl.pack(anchor=tk.W, pady=(3, 0))

    def create_controls_section(self, parent):
        ctrl_frame = tk.LabelFrame(parent, text="🚀 One-Click Game & Match Controls",
                                   bg="#0f1419", fg="#00ff41",
                                   font=("Segoe UI", 11, "bold"),
                                   padx=12, pady=12)
        ctrl_frame.pack(fill=tk.X, pady=(0, 15))

        # Row 1: Launch HLDS + Launch Game Client + Auto-Connect
        r1 = tk.Frame(ctrl_frame, bg="#0f1419")
        r1.pack(fill=tk.X, pady=(0, 10))

        btn_hlds = tk.Button(r1, text="🖥️ 1. Start Server",
                             bg="#2563eb", fg="white", font=("Segoe UI", 10, "bold"),
                             padx=10, pady=8, relief=tk.RAISED, cursor="hand2",
                             command=self.action_start_hlds)
        btn_hlds.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 6))

        btn_game = tk.Button(r1, text="🎮 2. Launch CS 1.6",
                             bg="#059669", fg="white", font=("Segoe UI", 10, "bold"),
                             padx=10, pady=8, relief=tk.RAISED, cursor="hand2",
                             command=self.action_launch_game)
        btn_game.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 6))

        btn_connect = tk.Button(r1, text="🔌 3. Auto-Connect",
                                bg="#7c3aed", fg="white", font=("Segoe UI", 10, "bold"),
                                padx=10, pady=8, relief=tk.RAISED, cursor="hand2",
                                command=self.action_auto_connect)
        btn_connect.pack(side=tk.LEFT, expand=True, fill=tk.X)

        # Row 2: Match Start / Force Live / Stop Match
        r2 = tk.Frame(ctrl_frame, bg="#0f1419")
        r2.pack(fill=tk.X, pady=(0, 8))

        btn_start_match = tk.Button(r2, text="🔥 4. Start Match",
                                    bg="#f59e0b", fg="black", font=("Segoe UI", 10, "bold"),
                                    padx=10, pady=8, relief=tk.RAISED, cursor="hand2",
                                    command=self.action_start_match)
        btn_start_match.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 6))

        btn_force_live = tk.Button(r2, text="⚡ 5. Force LIVE (/start)",
                                   bg="#10b981", fg="black", font=("Segoe UI", 10, "bold"),
                                   padx=10, pady=8, relief=tk.RAISED, cursor="hand2",
                                   command=self.action_force_live)
        btn_force_live.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 6))

        btn_stop_match = tk.Button(r2, text="⏹️ Stop Match",
                                   bg="#dc2626", fg="white", font=("Segoe UI", 10, "bold"),
                                   padx=10, pady=8, relief=tk.RAISED, cursor="hand2",
                                   command=self.action_stop_match)
        btn_stop_match.pack(side=tk.LEFT, expand=True, fill=tk.X)

        # Row 3: Open Overlays in Browser
        r3 = tk.Frame(ctrl_frame, bg="#0f1419")
        r3.pack(fill=tk.X)

        btn_open_tournament = tk.Button(r3, text="🏆 Open Tournament HUD (Weapons + HP + Scores)",
                                        bg="#1e293b", fg="#38bdf8", font=("Segoe UI", 9, "bold"),
                                        pady=6, relief=tk.RAISED, cursor="hand2",
                                        command=self.action_open_tournament_overlay)
        btn_open_tournament.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 6))

        btn_open_overlay = tk.Button(r3, text="🌐 Scoreboard Only",
                                     bg="#334155", fg="#cbd5e1", font=("Segoe UI", 9, "bold"),
                                     pady=6, relief=tk.RAISED, cursor="hand2",
                                     command=self.action_open_overlay)
        btn_open_overlay.pack(side=tk.LEFT, fill=tk.X)

        # Row 4: Screenshots Folder
        r4 = tk.Frame(ctrl_frame, bg="#0f1419")
        r4.pack(fill=tk.X, pady=(6, 0))

        btn_open_screenshots = tk.Button(r4, text="📁 Open Screenshots Folder (Counter-Strike WaRzOnE/Screenshots)",
                                         bg="#1e293b", fg="#10b981", font=("Segoe UI", 9, "bold"),
                                         pady=6, relief=tk.RAISED, cursor="hand2",
                                         command=self.action_open_screenshots)
        btn_open_screenshots.pack(fill=tk.X)

    def create_map_section(self, parent):
        map_frame = tk.LabelFrame(parent, text="🗺️ Tournament Map Selection (Click to Switch Map)",
                                  bg="#0f1419", fg="#38bdf8",
                                  font=("Segoe UI", 11, "bold"),
                                  padx=12, pady=10)
        map_frame.pack(fill=tk.X, pady=(0, 15))

        maps_row = tk.Frame(map_frame, bg="#0f1419")
        maps_row.pack(fill=tk.X)

        maps_data = [
            ("🏜️ de_dust2", "de_dust2"),
            ("🏰 de_inferno", "de_inferno"),
            ("☢️ de_nuke", "de_nuke")
        ]

        for label_text, map_key in maps_data:
            btn = tk.Button(
                maps_row, text=label_text,
                bg="#1e293b", fg="#e2e8f0",
                font=("Segoe UI", 10, "bold"),
                padx=10, pady=8, relief=tk.RAISED, cursor="hand2",
                command=lambda m=map_key: self.action_change_map(m)
            )
            btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=4)
            self.map_buttons[map_key] = btn

        self.update_map_button_styles()

    def update_map_button_styles(self):
        curr = self.selected_map.get()
        for map_key, btn in self.map_buttons.items():
            if map_key == curr:
                btn.configure(
                    bg="#0284c7", fg="#ffffff",
                    relief=tk.SUNKEN, bd=2,
                    font=("Segoe UI", 10, "bold")
                )
            else:
                btn.configure(
                    bg="#1e293b", fg="#94a3b8",
                    relief=tk.RAISED, bd=1,
                    font=("Segoe UI", 10, "normal")
                )

    def action_change_map(self, map_name):
        """Switches map on the running server, or sets active map for next launch"""
        self.selected_map.set(map_name)
        self.update_map_button_styles()

        if is_hlds_online():
            self.show_status(f"⏳ Switching server map to {map_name}...", "#f59e0b")
            ok, res = send_rcon_cmd(f"changelevel {map_name}")
            if ok:
                self.show_status(f"🗺️ Map switched to {map_name} successfully!", "#00ff41")
            else:
                self.show_status(f"⚠️ Sent changelevel {map_name}: {res}", "#38bdf8")
        else:
            self.show_status(f"🗺️ Active Map: {map_name} (Server will boot on this map)", "#38bdf8")

    def get_current_friendly_fire(self):
        """Reads current mp_friendlyfire setting from server.cfg"""
        server_cfg = os.path.join(CSTRIKE_DIR, "server.cfg")
        if os.path.exists(server_cfg):
            try:
                with open(server_cfg, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                m = re.search(r"mp_friendlyfire\s+([01])", content)
                if m:
                    return int(m.group(1))
            except Exception:
                pass
        return 0

    def create_rules_section(self, parent):
        rules_frame = tk.LabelFrame(parent, text="⚙️ Match & Server Rules",
                                    bg="#0f1419", fg="#f59e0b",
                                    font=("Segoe UI", 11, "bold"),
                                    padx=12, pady=10)
        rules_frame.pack(fill=tk.X, pady=(0, 15))

        r_row = tk.Frame(rules_frame, bg="#0f1419")
        r_row.pack(fill=tk.X)

        lbl = tk.Label(r_row, text="🛡️ Friendly Fire (Teammate Damage):",
                       bg="#0f1419", fg="#e2e8f0", font=("Segoe UI", 10, "bold"))
        lbl.pack(side=tk.LEFT, padx=(0, 10))

        self.btn_ff = tk.Button(
            r_row, text="🛡️ Friendly Fire: OFF",
            bg="#1e293b", fg="#94a3b8",
            font=("Segoe UI", 10, "bold"),
            padx=16, pady=6, relief=tk.RAISED, cursor="hand2",
            command=self.action_toggle_friendly_fire
        )
        self.btn_ff.pack(side=tk.RIGHT)
        self.update_ff_button_style()

    def update_ff_button_style(self):
        if not hasattr(self, "btn_ff"):
            return
        is_on = self.friendly_fire.get() == 1
        if is_on:
            self.btn_ff.configure(
                text="⚔️ Friendly Fire: ON",
                bg="#dc2626", fg="#ffffff",
                relief=tk.SUNKEN, bd=2
            )
        else:
            self.btn_ff.configure(
                text="🛡️ Friendly Fire: OFF",
                bg="#1e293b", fg="#94a3b8",
                relief=tk.RAISED, bd=1
            )

    def save_cvar_to_cfg(self, cfg_path, cvar_name, value):
        """Helper to safely replace or add a cvar in a .cfg file"""
        if not os.path.exists(cfg_path):
            return
        try:
            with open(cfg_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            pattern = rf"^({re.escape(cvar_name)}\s+)\d+"
            if re.search(pattern, content, flags=re.MULTILINE):
                new_content = re.sub(pattern, rf"\g<1>{value}", content, flags=re.MULTILINE)
            else:
                new_content = content + f"\n{cvar_name} {value}\n"
            with open(cfg_path, "w", encoding="utf-8") as f:
                f.write(new_content)
        except Exception as e:
            print(f"Error updating {cfg_path}: {e}")

    def action_toggle_friendly_fire(self):
        """Toggles friendly fire ON/OFF, updates configs, and sends live RCON if server is online"""
        curr = self.friendly_fire.get()
        new_val = 0 if curr == 1 else 1
        self.friendly_fire.set(new_val)
        self.update_ff_button_style()

        # Update server.cfg and league configs so matches maintain setting
        self.save_cvar_to_cfg(os.path.join(CSTRIKE_DIR, "server.cfg"), "mp_friendlyfire", str(new_val))
        self.save_cvar_to_cfg(os.path.join(CSTRIKE_DIR, "addons", "amxmodx", "configs", "amxmd", "leagues", "cal.cfg"), "mp_friendlyfire", str(new_val))
        self.save_cvar_to_cfg(os.path.join(CSTRIKE_DIR, "addons", "amxmodx", "configs", "amxmd", "leagues", "ffa.cfg"), "mp_friendlyfire", str(new_val))

        state_str = "ENABLED (Damage ON)" if new_val == 1 else "DISABLED (Damage OFF)"
        color = "#ef4444" if new_val == 1 else "#10b981"

        if is_hlds_online():
            send_rcon_cmd(f"mp_friendlyfire {new_val}")
            send_rcon_cmd(f'say [SERVER] Friendly Fire is now {state_str}')
            self.show_status(f"⚔️ Friendly Fire {state_str} live on server!", color)
        else:
            self.show_status(f"💾 Friendly Fire saved as {state_str} (will apply on launch)", color)

    def create_team_section(self, parent):
        team_frame = tk.LabelFrame(parent, text="Team Names",
                                   bg="#0f1419", fg="#00ccff",
                                   font=("Segoe UI", 11, "bold"),
                                   padx=12, pady=10)
        team_frame.pack(fill=tk.X, pady=(0, 15))

        # Team 1
        t1 = tk.Frame(team_frame, bg="#0f1419")
        t1.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(t1, text="Team 1 Name:", style="Dark.TLabel").pack(side=tk.LEFT)
        entry1 = ttk.Entry(t1, textvariable=self.team_names["team1"], style="Dark.TEntry", width=28)
        entry1.pack(side=tk.RIGHT)
        entry1.bind("<KeyRelease>", lambda e: self.update_preview())

        # Team 2
        t2 = tk.Frame(team_frame, bg="#0f1419")
        t2.pack(fill=tk.X)
        ttk.Label(t2, text="Team 2 Name:", style="Dark.TLabel").pack(side=tk.LEFT)
        entry2 = ttk.Entry(t2, textvariable=self.team_names["team2"], style="Dark.TEntry", width=28)
        entry2.pack(side=tk.RIGHT)
        entry2.bind("<KeyRelease>", lambda e: self.update_preview())

    def create_colors_section(self, parent):
        colors_frame = tk.LabelFrame(parent, text="Colors",
                                     bg="#0f1419", fg="#00ccff",
                                     font=("Segoe UI", 11, "bold"),
                                     padx=12, pady=10)
        colors_frame.pack(fill=tk.X, pady=(0, 15))

        color_configs = [
            ("Team 1 Color:", "team1"),
            ("Team 2 Color:", "team2"),
            ("Status Color (LIVE):", "status"),
            ("Border Color:", "border")
        ]

        for label_text, color_key in color_configs:
            row = tk.Frame(colors_frame, bg="#0f1419")
            row.pack(fill=tk.X, pady=4)

            ttk.Label(row, text=label_text, style="Dark.TLabel").pack(side=tk.LEFT)

            btn = tk.Button(row, text="🎨 Pick Color",
                            bg=self.colors[color_key],
                            fg=self.get_contrast_color(self.colors[color_key]),
                            font=("Segoe UI", 9, "bold"),
                            width=14, height=1, relief=tk.RAISED, cursor="hand2",
                            command=lambda k=color_key: self.pick_color(k))
            btn.pack(side=tk.RIGHT)
            setattr(self, f"{color_key}_button", btn)

    def create_preview_section(self, parent):
        preview_frame = tk.LabelFrame(parent, text="Live Preview",
                                      bg="#0f1419", fg="#00ccff",
                                      font=("Segoe UI", 11, "bold"),
                                      padx=12, pady=10)
        preview_frame.pack(fill=tk.X, pady=(0, 15))

        self.preview_container = tk.Frame(preview_frame, bg="#001428", relief=tk.RAISED, bd=2)
        self.preview_container.pack(fill=tk.X, pady=5)

        self.status_label = tk.Label(self.preview_container, text="LIVE",
                                     bg="#001428", fg=self.colors["status"],
                                     font=("Segoe UI", 9, "bold"))
        self.status_label.pack(pady=(8, 3))

        teams_frame = tk.Frame(self.preview_container, bg="#001428")
        teams_frame.pack(pady=(0, 8))

        self.team1_label = tk.Label(teams_frame, text="Aimbots 15",
                                    bg="#001428", fg=self.colors["team1"],
                                    font=("Segoe UI", 15, "bold"))
        self.team1_label.pack(side=tk.LEFT, padx=15)

        vs_lbl = tk.Label(teams_frame, text="VS", bg="#001428", fg="#888888", font=("Segoe UI", 13, "bold"))
        vs_lbl.pack(side=tk.LEFT, padx=10)

        self.team2_label = tk.Label(teams_frame, text="Deadshot 12",
                                    bg="#001428", fg=self.colors["team2"],
                                    font=("Segoe UI", 15, "bold"))
        self.team2_label.pack(side=tk.LEFT, padx=15)

    def create_buttons_section(self, parent):
        btn_frame = tk.Frame(parent, bg="#121824")
        btn_frame.pack(fill=tk.X, pady=(0, 10))

        save_btn = tk.Button(btn_frame, text="💾 Save Configuration",
                             bg="#00ff41", fg="black", font=("Segoe UI", 12, "bold"),
                             padx=20, pady=10, relief=tk.RAISED, cursor="hand2",
                             command=self.save_config)
        save_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 8))

        reset_btn = tk.Button(btn_frame, text="🔄 Reset Defaults",
                              bg="#ff4757", fg="white", font=("Segoe UI", 12, "bold"),
                              padx=20, pady=10, relief=tk.RAISED, cursor="hand2",
                              command=self.reset_defaults)
        reset_btn.pack(side=tk.LEFT, expand=True, fill=tk.X)

        self.status_text = tk.Label(parent, text="Ready - Configure your team settings above",
                                    bg="#121824", fg="#38bdf8", font=("Segoe UI", 9))
        self.status_text.pack(pady=(5, 10))

    # --- Actions ---
    def action_start_hlds(self):
        """Starts HLDS server on the best available port (auto-detects 27015, 27016, etc.)"""
        active_p = find_active_hlds_port()
        if active_p:
            self.show_status(f"⚠️ HLDS Server is ALREADY running on port {active_p}!", "#f59e0b")
            messagebox.showinfo("Server Already Running", f"HLDS is already active on port {active_p}!")
            return

        port_to_use = get_available_port(preferred_port=27016)
        global CURRENT_PORT
        CURRENT_PORT = port_to_use

        current_map = self.selected_map.get() if hasattr(self, "selected_map") else MAP_NAME
        cmd = [
            HLDS_EXE,
            "-console",
            "-game", "cstrike",
            "+port", str(port_to_use),
            "+maxplayers", str(MAX_PLAYERS),
            "+map", current_map,
            "+hostname", HOSTNAME,
            "+rcon_password", RCON_PASS,
            "+mp_friendlyfire", str(self.friendly_fire.get()),
            "-insecure",
            "-nomaster"
        ]
        try:
            flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
            subprocess.Popen(cmd, cwd=BASE_DIR, creationflags=flags)
            self.show_status(f"🚀 HLDS Launched on Port {port_to_use} ({current_map}, VAC Off)!", "#00ff41")
        except Exception as e:
            self.show_status(f"❌ Failed to launch HLDS: {e}", "#ff4757")

    def action_launch_game(self):
        """Launches CS 1.6 client using CS16Launcher.exe"""
        active_p = get_server_port()
        if os.path.exists(CS_LAUNCHER):
            cmd = [
                CS_LAUNCHER,
                "-steam",
                "-game", "cstrike",
                "-noforcemparms",
                "-noforcemaccel",
                "-clientport", "27005",
                "+clientport", "27005",
                "+port", "27015"
            ]
            try:
                subprocess.Popen(cmd, cwd=BASE_DIR)
                self.show_status(f"🎮 CS 1.6 Launched! In console: connect 127.0.0.1:{active_p}", "#00ff41")
            except Exception as e:
                self.show_status(f"❌ Failed to launch CS: {e}", "#ff4757")
        else:
            self.show_status("❌ CS16Launcher.exe not found!", "#ff4757")

    def action_auto_connect(self):
        """Auto-connects CS 1.6 client to detected/active server port directly"""
        # 1. Ensure HLDS server is started if offline
        active_p = find_active_hlds_port()
        if not active_p:
            port_to_use = get_available_port(preferred_port=27016)
            self.show_status(f"🚀 HLDS offline. Launching server on port {port_to_use}...", "#f59e0b")
            self.action_start_hlds()
        else:
            port_to_use = active_p

        connect_cmd = f"connect {SERVER_IP}:{port_to_use}"

        # Copy to clipboard for easy manual fallback
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(connect_cmd)
        except Exception:
            pass

        # 2. Check if CS 1.6 client (hl.exe) is already running
        client_hwnd = find_hl_client_window()

        if client_hwnd:
            # CS 1.6 is already running - bring to foreground and execute connect
            try:
                user32 = ctypes.windll.user32
                kernel32 = ctypes.windll.kernel32

                cur_thread = kernel32.GetCurrentThreadId()
                fore_thread = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None)
                if cur_thread != fore_thread:
                    user32.AttachThreadInput(cur_thread, fore_thread, True)
                    user32.ShowWindow(client_hwnd, 9)  # SW_RESTORE
                    user32.SetForegroundWindow(client_hwnd)
                    user32.AttachThreadInput(cur_thread, fore_thread, False)
                else:
                    user32.ShowWindow(client_hwnd, 9)
                    user32.SetForegroundWindow(client_hwnd)

                time.sleep(0.5)

                # 1. Trigger F7 bind (in-game)
                send_key(0x76)  # VK_F7
                time.sleep(0.1)

                # 2. Open console, paste connect, and submit (works in main menu!)
                VK_OEM_3 = 0xC0  # ~ / ` key
                VK_RETURN = 0x0D
                send_key(VK_OEM_3)
                time.sleep(0.1)
                send_paste()
                time.sleep(0.1)
                send_key(VK_RETURN)

                self.show_status(f"🔌 Connected! Sent connect {SERVER_IP}:{port_to_use} to CS 1.6", "#00ff41")
            except Exception:
                self.show_status(f"🔌 CS focused! Paste '{connect_cmd}' in console (already copied)", "#38bdf8")
        else:
            # CS 1.6 is not running - write connect command into userconfig.cfg and autoexec.cfg
            # config.cfg runs 'exec userconfig.cfg' on game startup, which immediately connects!
            userconfig_connect = (
                'console "1.0"\n'
                'rate "20000"\n'
                'fps_max "100"\n'
                f'bind "F7" "{connect_cmd}"\n'
                f'{connect_cmd}\n'
            )
            try:
                with open(USERCONFIG_PATH, "w", encoding="utf-8") as f:
                    f.write(userconfig_connect)
                with open(AUTOEXEC_PATH, "w", encoding="utf-8") as f:
                    f.write(f"{connect_cmd}\n")
            except Exception:
                pass

            # Launch game client via CS16Launcher or hl.exe
            exe_to_launch = CS_LAUNCHER if os.path.exists(CS_LAUNCHER) else HL_EXE
            cmd = [
                exe_to_launch,
                "-steam",
                "-game", "cstrike",
                "-noforcemparms",
                "-noforcemaccel",
                "-clientport", "27005",
                "+clientport", "27005",
                "+port", "27015",
                "+connect", f"{SERVER_IP}:{port_to_use}"
            ]
            try:
                subprocess.Popen(cmd, cwd=BASE_DIR)
                self.show_status(f"🎮 Opening CS 1.6 & Connecting to Port {port_to_use}...", "#00ff41")
            except Exception as e:
                self.show_status(f"❌ Failed to launch CS: {e}", "#ff4757")

            # Clean up userconfig.cfg after 10 seconds so future launches don't force auto-connect
            def clean_userconfig():
                try:
                    clean_content = (
                        'console "1.0"\n'
                        'rate "20000"\n'
                        'cl_cmdbackup "2"\n'
                        'cl_cmdrate "105"\n'
                        'cl_dlmax "1024"\n'
                        'cl_updaterate "100"\n'
                        'fps_max "100"\n'
                        f'bind "F7" "{connect_cmd}"\n'
                    )
                    with open(USERCONFIG_PATH, "w", encoding="utf-8") as f:
                        f.write(clean_content)
                    with open(AUTOEXEC_PATH, "w", encoding="utf-8") as f:
                        f.write("// Ready\n")
                except Exception:
                    pass

            self.root.after(10000, clean_userconfig)

    def action_start_match(self):
        """Saves current config and starts/restarts match cleanly"""
        self.save_config()
        t1 = self.team_names["team1"].get().strip().replace('"', '').replace(" ", "_") or "Team1"
        t2 = self.team_names["team2"].get().strip().replace('"', '').replace(" ", "_") or "Team2"

        # If HLDS server is offline, start it first
        if not is_hlds_online():
            self.show_status(f"⚠️ HLDS offline! Starting server first...", "#f59e0b")
            self.action_start_hlds()
            time.sleep(1.0)

        # Stop any existing match cleanly first to avoid 'match already in progress' lock
        send_rcon_cmd("amx_matchstop")
        time.sleep(0.3)

        match_cmd = f"amx_match {t1} {t2} mr15 cal"
        ok, res = send_rcon_cmd(match_cmd)
        if ok:
            self.show_status(f"🔥 Match Started: {t1} vs {t2} (Warmup active - press Force LIVE to play)!", "#00ff41")
        else:
            self.show_status(f"❌ Could not start match: {res}", "#ff4757")

    def action_force_live(self):
        """Forces warmup to end and goes LIVE immediately"""
        if not is_hlds_online():
            self.show_status("❌ HLDS Server is OFFLINE! Click Start Server first.", "#ff4757")
            return

        ok, res = send_rcon_cmd("amx_matchstart")
        if ok:
            self.show_status("⚡ Match forced LIVE! 3 round restarts executing...", "#00ff41")
        else:
            self.show_status(f"❌ Force LIVE error: {res}", "#ff4757")

    def action_stop_match(self):
        """Stops the current match"""
        ok, res = send_rcon_cmd("amx_matchstop")
        if ok:
            self.show_status("⏹️ Match stopped successfully.", "#f59e0b")
        else:
            self.show_status(f"❌ Stop match error: {res}", "#ff4757")

    def action_open_tournament_overlay(self):
        """Opens tournament_overlay.html in browser"""
        url = "file:///" + TOURNAMENT_OVERLAY_HTML_PATH.replace("\\", "/")
        webbrowser.open(url)
        self.show_status("🏆 Opened Tournament HUD in browser!", "#38bdf8")

    def action_open_player_hud(self):
        """Opens player_hud.html in browser"""
        url = "file:///" + PLAYER_HUD_HTML_PATH.replace("\\", "/")
        webbrowser.open(url)
        self.show_status("👥 Opened Player HUD in browser!", "#38bdf8")

    def action_open_overlay(self):
        """Opens live_overlay.html in browser"""
        url = "file:///" + LIVE_OVERLAY_HTML_PATH.replace("\\", "/")
        webbrowser.open(url)
        self.show_status("🌐 Opened live_overlay.html in browser!", "#38bdf8")

    def action_open_screenshots(self):
        """Opens the Counter-Strike WaRzOnE/Screenshots directory in Windows Explorer"""
        if not os.path.exists(SCREENSHOTS_DIR):
            os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
        try:
            os.startfile(SCREENSHOTS_DIR)
            self.show_status("📁 Opened Screenshots folder!", "#10b981")
        except Exception as e:
            self.show_status(f"❌ Error opening Screenshots folder: {e}", "#ff4757")

    def route_screenshots(self):
        """Automatically moves any newly captured .bmp or .tga screenshots from cstrike into Screenshots/"""
        try:
            if not os.path.exists(SCREENSHOTS_DIR):
                os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
            for f in os.listdir(CSTRIKE_DIR):
                if f.lower().endswith((".bmp", ".tga")):
                    src = os.path.join(CSTRIKE_DIR, f)
                    if os.path.isfile(src):
                        try:
                            dst = os.path.join(SCREENSHOTS_DIR, f)
                            if os.path.exists(dst):
                                base, ext = os.path.splitext(f)
                                dst = os.path.join(SCREENSHOTS_DIR, f"{base}_{int(time.time())}{ext}")
                            shutil.move(src, dst)
                        except Exception:
                            pass
        except Exception:
            pass

    # --- Polling & Background Updates ---
    def poll_status(self):
        """Checks HLDS server & match status every 1.5 seconds"""
        active_p = find_active_hlds_port()
        current_map = self.selected_map.get() if hasattr(self, "selected_map") else MAP_NAME
        if active_p:
            self.server_status_lbl.config(
                text=f"🖥️ HLDS Server: ONLINE (Port {active_p} | Map: {current_map})",
                fg="#00ff41"
            )
        else:
            ready_p = get_available_port(preferred_port=27016)
            self.server_status_lbl.config(
                text=f"🖥️ HLDS Server: OFFLINE (Ready on Port {ready_p} | Map: {current_map})",
                fg="#ff4757"
            )

        # Read live score file
        if os.path.exists(LIVE_SCORES_PATH):
            try:
                with open(LIVE_SCORES_PATH, "r", encoding="utf-8") as f:
                    parts = f.read().strip().split("|")
                    if len(parts) >= 5:
                        t1, s1, t2, s2, st = parts[0], parts[1], parts[2], parts[3], parts[4]
                        self.match_status_lbl.config(
                            text=f"⚔️ Match State: {st} | {t1} [{s1}] vs [{s2}] {t2}",
                            fg="#38bdf8" if st != "LIVE" else "#ff4757"
                        )
            except Exception:
                pass

        # Auto-route any snapshots from cstrike into Screenshots/
        self.route_screenshots()

        self.root.after(1500, self.poll_status)

    # --- UI Helpers ---
    def pick_color(self, color_key):
        curr = self.colors[color_key]
        res = colorchooser.askcolor(color=curr, title=f"Choose {color_key.title()} Color")
        if res[1]:
            new_c = res[1]
            self.colors[color_key] = new_c
            btn = getattr(self, f"{color_key}_button")
            btn.configure(bg=new_c, fg=self.get_contrast_color(new_c))
            self.update_preview()

    def get_contrast_color(self, hex_color):
        hex_color = hex_color.lstrip("#")
        try:
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255
            return "#000000" if lum > 0.5 else "#FFFFFF"
        except Exception:
            return "#FFFFFF"

    def hex_to_rgb(self, hex_color):
        hex_color = hex_color.lstrip("#")
        try:
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            return f"{r},{g},{b}"
        except Exception:
            return "255,255,255"

    def rgb_str_to_hex(self, rgb_str):
        try:
            parts = [int(x.strip()) for x in rgb_str.split(",")[:3] if x.strip().isdigit()]
            if len(parts) == 3:
                return f"#{parts[0]:02x}{parts[1]:02x}{parts[2]:02x}"
        except Exception:
            pass
        return None

    def update_preview(self):
        t1 = self.team_names["team1"].get() or "Team1"
        t2 = self.team_names["team2"].get() or "Team2"

        self.team1_label.config(text=f"{t1} 15", fg=self.colors["team1"])
        self.team2_label.config(text=f"{t2} 12", fg=self.colors["team2"])
        self.status_label.config(fg=self.colors["status"])

        self.preview_container.config(highlightbackground=self.colors["border"], highlightthickness=2)

    def load_config(self):
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    content = f.read()

                m1 = re.search(r"team1_display_name=(.+)", content)
                m2 = re.search(r"team2_display_name=(.+)", content)
                if m1: self.team_names["team1"].set(m1.group(1).strip())
                if m2: self.team_names["team2"].set(m2.group(1).strip())

                c1 = re.search(r"default_text_color=([0-9, ]+)", content)
                c2 = re.search(r"team2_color=([0-9, ]+)", content)
                st = re.search(r"status_color=([0-9, ]+)", content)
                bd = re.search(r"border_color=([0-9, ]+)", content)

                if c1 and self.rgb_str_to_hex(c1.group(1)): self.colors["team1"] = self.rgb_str_to_hex(c1.group(1))
                if c2 and self.rgb_str_to_hex(c2.group(1)): self.colors["team2"] = self.rgb_str_to_hex(c2.group(1))
                if st and self.rgb_str_to_hex(st.group(1)): self.colors["status"] = self.rgb_str_to_hex(st.group(1))
                if bd and self.rgb_str_to_hex(bd.group(1)): self.colors["border"] = self.rgb_str_to_hex(bd.group(1))

                for k in self.colors:
                    btn = getattr(self, f"{k}_button", None)
                    if btn:
                        btn.configure(bg=self.colors[k], fg=self.get_contrast_color(self.colors[k]))

                self.show_status("✅ Configuration loaded successfully!", "#00ff41")
        except Exception as e:
            self.show_status(f"❌ Error loading config: {e}", "#ff4757")

    def save_config(self):
        try:
            if not os.path.exists(self.config_path):
                return

            with open(self.config_path, "r", encoding="utf-8") as f:
                content = f.read()

            t1 = self.team_names["team1"].get().strip() or "Team1"
            t2 = self.team_names["team2"].get().strip() or "Team2"

            content = re.sub(r"team1_display_name=.*", f"team1_display_name={t1}", content)
            content = re.sub(r"team2_display_name=.*", f"team2_display_name={t2}", content)
            content = re.sub(r"default_text_color=.*", f"default_text_color={self.hex_to_rgb(self.colors['team1'])}", content)
            content = re.sub(r"team2_color=.*", f"team2_color={self.hex_to_rgb(self.colors['team2'])}", content)
            content = re.sub(r"status_color=.*", f"status_color={self.hex_to_rgb(self.colors['status'])}", content)
            content = re.sub(r"border_color=.*", f"border_color={self.hex_to_rgb(self.colors['border'])}", content)

            with open(self.config_path, "w", encoding="utf-8") as f:
                f.write(content)

            # Preserve current scores
            s1, s2, st = 0, 0, "WAITING"
            if os.path.exists(LIVE_SCORES_PATH):
                try:
                    with open(LIVE_SCORES_PATH, "r", encoding="utf-8") as f:
                        parts = f.read().strip().split("|")
                        if len(parts) >= 5:
                            s1 = int(parts[1]) if parts[1].isdigit() else 0
                            s2 = int(parts[3]) if parts[3].isdigit() else 0
                            st = parts[4] or "WAITING"
                except Exception:
                    pass

            with open(LIVE_SCORES_PATH, "w", encoding="utf-8") as f:
                f.write(f"{t1}|{s1}|{t2}|{s2}|{st}|{self.colors['team1']}|{self.colors['team2']}|{self.colors['border']}|{self.colors['status']}\n")

            with open(SCORE_TXT_PATH, "w", encoding="utf-8") as f:
                f.write(f"{t1} {s1}       {t2} {s2}\n")

            with open(LIVE_DATA_JS_PATH, "w", encoding="utf-8") as f:
                f.write(f"window.setScores('{t1}',{s1},'{t2}',{s2},'{st}','{self.colors['team1']}','{self.colors['team2']}','{self.colors['border']}','{self.colors['status']}');\n")

            self.show_status(f"✅ Saved & Updated! Teams: {t1} vs {t2}", "#00ff41")
        except Exception as e:
            self.show_status(f"❌ Error saving: {e}", "#ff4757")

    def reset_defaults(self):
        self.team_names["team1"].set("Team1")
        self.team_names["team2"].set("Team2")
        self.colors = {
            "team1": "#00ff41",
            "team2": "#ff4757",
            "status": "#ffaa00",
            "border": "#00ff41"
        }
        for k in self.colors:
            btn = getattr(self, f"{k}_button", None)
            if btn:
                btn.configure(bg=self.colors[k], fg=self.get_contrast_color(self.colors[k]))
        self.update_preview()
        self.show_status("🔄 Reset to default values!", "#38bdf8")

    def show_status(self, message, color="#38bdf8"):
        self.status_text.config(text=message, fg=color)
        self.root.after(6000, lambda: self.status_text.config(
            text="Ready - Configure teams and control your match above", fg="#64748b"))


def main():
    root = tk.Tk()
    app = CSControlCenter(root)
    root.update_idletasks()
    w = root.winfo_width()
    h = root.winfo_height()
    x = (root.winfo_screenwidth() // 2) - (w // 2)
    y = (root.winfo_screenheight() // 2) - (h // 2)
    root.geometry(f"{w}x{h}+{x}+{y}")
    root.mainloop()


if __name__ == "__main__":
    main()
