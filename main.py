import sys
import os
import json
import shutil
import re
import random
import webbrowser
import urllib.request
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl, pyqtSignal, QThread, QObject, QFileInfo
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSlider, QListWidget, QListWidgetItem,
    QFileDialog, QDialog, QLineEdit, QComboBox, QColorDialog,
    QMessageBox, QFrame, QProgressBar, QInputDialog, QMenu, QGridLayout,
    QFileIconProvider
)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaDevices, QAudioDevice

DISCORD_CLIENT_ID = "1552402566283796601"

try:
    from pypresence import Presence
    DISCORD_AVAILABLE = True
except ImportError:
    DISCORD_AVAILABLE = False

try:
    import keyboard
    KEYBOARD_AVAILABLE = True
except ImportError:
    KEYBOARD_AVAILABLE = False

APP_DIR = Path.home() / "kalel_music"
TRACKS_DIR = APP_DIR / "tracks"
SETTINGS_FILE = APP_DIR / "settings.json"
LIBRARY_FILE = APP_DIR / "library.json"

APP_DIR.mkdir(parents=True, exist_ok=True)
TRACKS_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_THEMES = {
    "Cyber Cyan": {
        "bg": "#060b13",
        "card": "#121c2d",
        "accent": "#38bdf8",
        "text": "#ffffff",
        "text_muted": "#8292a8"
    },
    "Midnight Purple": {
        "bg": "#090714",
        "card": "#17122b",
        "accent": "#a855f7",
        "text": "#ffffff",
        "text_muted": "#94a3b8"
    },
    "Emerald": {
        "bg": "#060e0a",
        "card": "#11241a",
        "accent": "#10b981",
        "text": "#ffffff",
        "text_muted": "#6ee7b7"
    },
    "Onyx Dark": {
        "bg": "#0d0d0d",
        "card": "#1a1a1a",
        "accent": "#e5e5e5",
        "text": "#ffffff",
        "text_muted": "#737373"
    }
}

DEFAULT_SETTINGS = {
    "current_theme": "Cyber Cyan",
    "custom_colors": DEFAULT_THEMES["Cyber Cyan"].copy(),
    "volume": 70,
    "mic_volume": 80,
    "output_device": "",
    "mic_device": "Отключено",
    "output_mode": "both",
    "repeat_mode": "all",
    "shuffle": False,
    "hotkeys": {
        "play_pause": "f3",
        "next_track": "f4",
        "prev_track": "f2",
        "random_track": "",
        "route_both": "f6",
        "route_speakers": "f7",
        "route_mic": "f8"
    }
}


def is_virtual_cable_name(name):
    low = name.lower()
    return any(k in low for k in ["cable", "virtual", "voicemeeter", "line", "микшер", "stereo mix"])


class HotkeySignal(QObject):
    action_triggered = pyqtSignal(str)


class DiscordManager:
    def __init__(self, client_id):
        self.client_id = client_id
        self.rpc = None
        self.connected = False

    def connect(self):
        if not DISCORD_AVAILABLE:
            return
        try:
            self.rpc = Presence(self.client_id)
            self.rpc.connect()
            self.connected = True
        except Exception:
            self.connected = False

    def update_status(self, track_name, is_playing=True):
        if not DISCORD_AVAILABLE:
            return
        if not self.connected:
            self.connect()
        if self.connected and self.rpc:
            try:
                state_text = "Воспроизводится" if is_playing else "На паузе"
                self.rpc.update(
                    details=track_name[:128],
                    state=state_text,
                    large_text="kalel music"
                )
            except Exception:
                self.connected = False

    def clear(self):
        if self.connected and self.rpc:
            try:
                self.rpc.clear()
            except Exception:
                pass


class DownloadWorker(QThread):
    finished_sig = pyqtSignal(bool, str)

    def __init__(self, raw_input):
        super().__init__()
        self.raw_input = raw_input

    def resolve_spotify(self, text):
        text = text.strip()
        if "<iframe" in text:
            match = re.search(r'src=["\']([^"\']+)["\']', text)
            if match:
                text = match.group(1)

        if "open.spotify.com" in text:
            clean_url = text.replace("/embed/", "/").split("?")[0]
            api_url = f"https://open.spotify.com/oembed?url={clean_url}"
            req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
            try:
                with urllib.request.urlopen(req, timeout=5) as response:
                    data = json.loads(response.read().decode())
                    title = data.get("title", "")
                    artist = data.get("author_name", "")
                    return f"ytsearch1:{artist} - {title} audio"
            except Exception as e:
                print("Ошибка Spotify oEmbed:", e)
        return text

    def run(self):
        try:
            import yt_dlp
            target_query = self.resolve_spotify(self.raw_input)
            out_template = str(TRACKS_DIR / "%(title)s.%(ext)s")
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': out_template,
                'noplaylist': True,
                'quiet': True,
                'no_warnings': True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(target_query, download=True)
                if 'entries' in info:
                    info = info['entries'][0]
                filename = ydl.prepare_filename(info)
                self.finished_sig.emit(True, filename)
        except Exception as e:
            self.finished_sig.emit(False, str(e))


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_app = parent
        self.setWindowTitle("Настройки kalel music")
        self.setFixedSize(580, 720)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        layout.addWidget(QLabel("Основное устройство (Наушники/Колонки для вас):"))
        self.output_combo = QComboBox()
        self.output_devices = QMediaDevices.audioOutputs()
        self.output_combo.addItem("По умолчанию системы", "")
        current_dev = self.main_app.settings.get("output_device", "")
        select_idx = 0
        for i, dev in enumerate(self.output_devices):
            name = dev.description()
            self.output_combo.addItem(name, name)
            if name == current_dev:
                select_idx = i + 1
        self.output_combo.setCurrentIndex(select_idx)
        self.output_combo.currentIndexChanged.connect(self.on_output_device_change)
        layout.addWidget(self.output_combo)

        layout.addWidget(QLabel("Виртуальный кабель для вещания в микрофон:"))
        self.mic_combo = QComboBox()
        self.mic_combo.addItem("Отключено", "Отключено")

        current_mic = self.main_app.settings.get("mic_device", "Отключено")
        mic_select_idx = 0
        virtual_found = 0

        for dev in self.output_devices:
            name = dev.description()
            if is_virtual_cable_name(name):
                virtual_found += 1
                self.mic_combo.addItem(f"{name}", name)
                if name == current_mic:
                    mic_select_idx = self.mic_combo.count() - 1

        for dev in self.output_devices:
            name = dev.description()
            if not is_virtual_cable_name(name):
                self.mic_combo.addItem(f"Другое: {name}", name)
                if name == current_mic and mic_select_idx == 0:
                    mic_select_idx = self.mic_combo.count() - 1

        self.mic_combo.setCurrentIndex(mic_select_idx)
        self.mic_combo.currentIndexChanged.connect(self.on_mic_device_change)
        layout.addWidget(self.mic_combo)

        if virtual_found == 0:
            warn_box = QHBoxLayout()
            warn_lbl = QLabel("Виртуальный кабель не найден. Нужен VB-CABLE для передачи звука в микрофон.")
            warn_lbl.setStyleSheet("color: #f87171; font-size: 11px;")
            warn_box.addWidget(warn_lbl)
            btn_dl = QPushButton("Установить VB-CABLE")
            btn_dl.clicked.connect(lambda: webbrowser.open("https://vb-audio.com/Cable/"))
            warn_box.addWidget(btn_dl)
            layout.addLayout(warn_box)

        input_devs = QMediaDevices.audioInputs()
        mic_names = [d.description() for d in input_devs]
        info_mic = QLabel("Микрофоны в вашей системе:\n" + ("\n".join(f"- {m}" for m in mic_names) if mic_names else "- Не найдены"))
        info_mic.setStyleSheet("color: #8292a8; font-size: 11px;")
        layout.addWidget(info_mic)

        mic_vol_layout = QHBoxLayout()
        mic_vol_layout.addWidget(QLabel("Громкость вещания:"))
        self.mic_vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.mic_vol_slider.setRange(0, 100)
        self.mic_vol_slider.setValue(self.main_app.settings.get("mic_volume", 80))
        self.mic_vol_lbl = QLabel(f"{self.mic_vol_slider.value()}%")
        self.mic_vol_slider.valueChanged.connect(self.on_mic_vol_change)
        mic_vol_layout.addWidget(self.mic_vol_slider)
        mic_vol_layout.addWidget(self.mic_vol_lbl)
        layout.addLayout(mic_vol_layout)

        layout.addWidget(QLabel("Глобальные бинды (работают даже в свернутом виде):"))
        binds_box = QGridLayout()
        self.bind_inputs = {}
        hotkey_labels = [
            ("play_pause", "Воспроизведение / Пауза"),
            ("next_track", "Следующий трек"),
            ("prev_track", "Предыдущий трек"),
            ("random_track", "Случайный трек"),
            ("route_both", "Вывод: Динамики + Микрофон"),
            ("route_speakers", "Вывод: Только динамики"),
            ("route_mic", "Вывод: Только микрофон")
        ]
        saved_hotkeys = self.main_app.settings.get("hotkeys", {})
        for idx, (action, label_text) in enumerate(hotkey_labels):
            lbl = QLabel(label_text + ":")
            edit = QLineEdit(saved_hotkeys.get(action, ""))
            edit.setPlaceholderText("f3, f4, f6...")
            binds_box.addWidget(lbl, idx, 0)
            binds_box.addWidget(edit, idx, 1)
            self.bind_inputs[action] = edit
        layout.addLayout(binds_box)

        layout.addWidget(QLabel("Темы:"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(list(DEFAULT_THEMES.keys()) + ["Пользовательская"])
        self.theme_combo.setCurrentText(self.main_app.settings.get("current_theme", "Cyber Cyan"))
        self.theme_combo.currentTextChanged.connect(self.on_theme_select)
        layout.addWidget(self.theme_combo)

        colors_grid = QHBoxLayout()
        for key, name in [("bg", "Фон"), ("card", "Карточки"), ("accent", "Акцент"), ("text", "Текст")]:
            btn = QPushButton(name)
            btn.clicked.connect(lambda checked, k=key: self.pick_color(k))
            colors_grid.addWidget(btn)
        layout.addLayout(colors_grid)

        backup_box = QHBoxLayout()
        btn_export = QPushButton("Экспорт настроек")
        btn_export.clicked.connect(self.export_settings)
        backup_box.addWidget(btn_export)

        btn_import = QPushButton("Импорт настроек")
        btn_import.clicked.connect(self.import_settings)
        backup_box.addWidget(btn_import)
        layout.addLayout(backup_box)

        layout.addStretch()
        btn_save = QPushButton("Сохранить и закрыть")
        btn_save.clicked.connect(self.save_and_close)
        layout.addWidget(btn_save)

    def on_output_device_change(self, idx):
        dev_name = self.output_combo.currentData()
        self.main_app.settings["output_device"] = dev_name
        self.main_app.apply_audio_devices()
        self.main_app.save_settings()

    def on_mic_device_change(self, idx):
        dev_name = self.mic_combo.currentData()
        self.main_app.settings["mic_device"] = dev_name
        self.main_app.apply_audio_devices()
        self.main_app.save_settings()

    def on_mic_vol_change(self, val):
        self.mic_vol_lbl.setText(f"{val}%")
        self.main_app.settings["mic_volume"] = val
        self.main_app.mic_audio_output.setVolume(val / 100.0)
        self.main_app.save_settings()

    def on_theme_select(self, theme_name):
        if theme_name in DEFAULT_THEMES:
            self.main_app.settings["current_theme"] = theme_name
            self.main_app.settings["custom_colors"] = DEFAULT_THEMES[theme_name].copy()
            self.main_app.apply_theme()
            self.main_app.save_settings()

    def pick_color(self, key):
        col = QColorDialog.getColor()
        if col.isValid():
            self.main_app.settings["current_theme"] = "Пользовательская"
            self.theme_combo.setCurrentText("Пользовательская")
            self.main_app.settings["custom_colors"][key] = col.name()
            self.main_app.apply_theme()
            self.main_app.save_settings()

    def export_settings(self):
        path, _ = QFileDialog.getSaveFileName(self, "Экспорт настроек", "kalel_settings.json", "JSON (*.json)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.main_app.settings, f, indent=4)
            QMessageBox.information(self, "Успех", "Настройки сохранены.")

    def import_settings(self):
        path, _ = QFileDialog.getOpenFileName(self, "Импорт настроек", "", "JSON (*.json)")
        if path:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    new_settings = json.load(f)
                    self.main_app.settings.update(new_settings)
                self.main_app.apply_theme()
                self.main_app.apply_audio_devices()
                self.main_app.register_hotkeys()
                self.main_app.save_settings()
                self.theme_combo.setCurrentText(self.main_app.settings.get("current_theme", "Пользовательская"))
                QMessageBox.information(self, "Успех", "Настройки загружены.")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Ошибка чтения: {e}")

    def save_and_close(self):
        new_hotkeys = {}
        for action, edit in self.bind_inputs.items():
            new_hotkeys[action] = edit.text().strip().lower()
        self.main_app.settings["hotkeys"] = new_hotkeys
        self.main_app.save_settings()
        self.main_app.register_hotkeys()
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("kalel music")

        # Если программа запущена из .exe, берем встроенную в файл иконку
        if getattr(sys, "frozen", False):
            self.setWindowIcon(QFileIconProvider().icon(QFileInfo(sys.executable)))

        self.resize(860, 760)

        self.library_data = {"playlists": {"Основной": []}, "current_playlist": "Основной"}
        self.current_track_idx = -1
        self.settings = self.load_settings()

        self.discord = DiscordManager(DISCORD_CLIENT_ID)
        self.discord.connect()

        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(self.settings.get("volume", 70) / 100.0)

        self.mic_player = QMediaPlayer()
        self.mic_audio_output = QAudioOutput()
        self.mic_player.setAudioOutput(self.mic_audio_output)
        self.mic_audio_output.setVolume(self.settings.get("mic_volume", 80) / 100.0)

        self.hotkey_signal = HotkeySignal()
        self.hotkey_signal.action_triggered.connect(self.handle_hotkey_action)

        self.init_ui()
        self.apply_theme()
        self.apply_audio_devices()
        self.load_library()
        self.apply_output_mode()
        self.update_output_buttons()
        self.register_hotkeys()

        self.player.positionChanged.connect(self.on_position_changed)
        self.player.durationChanged.connect(self.on_duration_changed)
        self.player.mediaStatusChanged.connect(self.on_media_status_changed)

    @property
    def current_playlist_name(self):
        return self.library_data.get("current_playlist", "Основной")

    @property
    def current_tracks(self):
        playlists = self.library_data.get("playlists", {})
        return playlists.get(self.current_playlist_name, [])

    def load_settings(self):
        if SETTINGS_FILE.exists():
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    defaults = DEFAULT_SETTINGS.copy()
                    defaults.update(data)
                    return defaults
            except Exception:
                pass
        return DEFAULT_SETTINGS.copy()

    def save_settings(self):
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(self.settings, f, indent=4)

    def register_hotkeys(self):
        if not KEYBOARD_AVAILABLE:
            return
        try:
            keyboard.unhook_all()
        except Exception:
            pass

        hotkeys = self.settings.get("hotkeys", {})
        for action, key in hotkeys.items():
            if key and key.strip():
                try:
                    keyboard.add_hotkey(
                        key.strip(),
                        lambda act=action: self.hotkey_signal.action_triggered.emit(act)
                    )
                except Exception as e:
                    print(f"Ошибка хоткея {key}: {e}")

    def handle_hotkey_action(self, action):
        if action == "play_pause":
            self.toggle_play()
        elif action == "next_track":
            self.next_track()
        elif action == "prev_track":
            self.prev_track()
        elif action == "random_track":
            self.play_random_track()
        elif action == "route_both":
            self.set_output_mode("both")
        elif action == "route_speakers":
            self.set_output_mode("speakers")
        elif action == "route_mic":
            self.set_output_mode("mic")

    def load_library(self):
        if LIBRARY_FILE.exists():
            try:
                with open(LIBRARY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.library_data = {"playlists": {"Основной": data}, "current_playlist": "Основной"}
                    else:
                        self.library_data = data
            except Exception:
                self.library_data = {"playlists": {"Основной": []}, "current_playlist": "Основной"}
        else:
            self.library_data = {"playlists": {"Основной": []}, "current_playlist": "Основной"}

        if "Основной" not in self.library_data.get("playlists", {}):
            self.library_data.setdefault("playlists", {})["Основной"] = []

        self.update_playlist_selector()
        self.refresh_track_list()

    def save_library(self):
        with open(LIBRARY_FILE, "w", encoding="utf-8") as f:
            json.dump(self.library_data, f, indent=4)

    def apply_audio_devices(self):
        devices = QMediaDevices.audioOutputs()
        out_name = self.settings.get("output_device", "")
        mic_name = self.settings.get("mic_device", "Отключено")

        selected_out = None
        if out_name:
            for d in devices:
                if d.description() == out_name:
                    selected_out = d
                    break
        self.audio_output.setDevice(selected_out if selected_out else QMediaDevices.defaultAudioOutput())

        if mic_name and mic_name != "Отключено":
            selected_mic = None
            for d in devices:
                if d.description() == mic_name:
                    selected_mic = d
                    break
            self.mic_audio_output.setDevice(selected_mic if selected_mic else QAudioDevice())
        else:
            self.mic_audio_output.setDevice(QAudioDevice())

        self.apply_output_mode()

    def is_mic_active(self):
        mic = self.settings.get("mic_device", "Отключено")
        return bool(mic and mic != "Отключено")

    def set_output_mode(self, mode):
        self.settings["output_mode"] = mode
        self.save_settings()
        self.apply_output_mode()
        self.update_output_buttons()

    def apply_output_mode(self):
        mode = self.settings.get("output_mode", "both")
        mic_ready = self.is_mic_active()

        if mode == "both":
            self.audio_output.setMuted(False)
            self.mic_audio_output.setMuted(not mic_ready)
            if mic_ready and self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                if self.mic_player.source() != self.player.source():
                    self.mic_player.setSource(self.player.source())
                self.mic_player.setPosition(self.player.position())
                self.mic_player.play()
        elif mode == "speakers":
            self.audio_output.setMuted(False)
            self.mic_audio_output.setMuted(True)
        elif mode == "mic":
            self.audio_output.setMuted(True)
            self.mic_audio_output.setMuted(not mic_ready)
            if mic_ready and self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                if self.mic_player.source() != self.player.source():
                    self.mic_player.setSource(self.player.source())
                self.mic_player.setPosition(self.player.position())
                self.mic_player.play()

    def update_output_buttons(self):
        mode = self.settings.get("output_mode", "both")
        c = self.settings.get("custom_colors", DEFAULT_THEMES["Cyber Cyan"])
        active_css = f"background-color: {c['accent']}; color: #000000; font-weight: 600;"
        default_css = f"background-color: {c['card']}; color: {c['text']};"

        self.btn_out_both.setStyleSheet(active_css if mode == "both" else default_css)
        self.btn_out_speakers.setStyleSheet(active_css if mode == "speakers" else default_css)
        self.btn_out_mic.setStyleSheet(active_css if mode == "mic" else default_css)

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(12)

        header = QHBoxLayout()
        self.title_lbl = QLabel("kalel")
        self.title_lbl.setObjectName("appTitle")
        header.addWidget(self.title_lbl)

        header.addStretch()

        self.btn_settings = QPushButton("Настройки")
        self.btn_settings.clicked.connect(self.open_settings)
        header.addWidget(self.btn_settings)
        main_layout.addLayout(header)

        playlist_bar = QHBoxLayout()
        playlist_bar.addWidget(QLabel("Плейлист:"))

        self.playlist_combo = QComboBox()
        self.playlist_combo.currentTextChanged.connect(self.on_playlist_changed)
        playlist_bar.addWidget(self.playlist_combo, 1)

        self.btn_add_playlist = QPushButton("Создать")
        self.btn_add_playlist.clicked.connect(self.create_playlist)
        playlist_bar.addWidget(self.btn_add_playlist)

        self.btn_del_playlist = QPushButton("Удалить")
        self.btn_del_playlist.clicked.connect(self.delete_current_playlist)
        playlist_bar.addWidget(self.btn_del_playlist)
        main_layout.addLayout(playlist_bar)

        actions_bar = QHBoxLayout()
        self.btn_add_file = QPushButton("Добавить MP3")
        self.btn_add_file.clicked.connect(self.import_local_file)
        actions_bar.addWidget(self.btn_add_file)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Ссылка Spotify, YouTube, SoundCloud...")
        actions_bar.addWidget(self.url_input)

        self.btn_add_url = QPushButton("Скачать")
        self.btn_add_url.clicked.connect(self.import_url)
        actions_bar.addWidget(self.btn_add_url)
        main_layout.addLayout(actions_bar)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 0)
        main_layout.addWidget(self.progress_bar)

        self.track_list_widget = QListWidget()
        self.track_list_widget.itemDoubleClicked.connect(self.play_selected_track)
        self.track_list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.track_list_widget.customContextMenuRequested.connect(self.show_context_menu)
        main_layout.addWidget(self.track_list_widget)

        player_box = QFrame()
        player_box.setObjectName("playerBox")
        player_layout = QVBoxLayout(player_box)
        player_layout.setSpacing(8)

        self.now_playing_lbl = QLabel("Нет воспроизводимого трека")
        self.now_playing_lbl.setObjectName("nowPlaying")
        player_layout.addWidget(self.now_playing_lbl)

        time_bar = QHBoxLayout()
        self.time_lbl = QLabel("0:00 / 0:00")
        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        self.seek_slider.sliderMoved.connect(self.set_position)
        time_bar.addWidget(self.seek_slider)
        time_bar.addWidget(self.time_lbl)
        player_layout.addLayout(time_bar)

        controls_bar = QHBoxLayout()
        self.btn_prev = QPushButton("Назад")
        self.btn_prev.clicked.connect(self.prev_track)
        controls_bar.addWidget(self.btn_prev)

        self.btn_play = QPushButton("Воспроизвести")
        self.btn_play.clicked.connect(self.toggle_play)
        controls_bar.addWidget(self.btn_play)

        self.btn_next = QPushButton("Вперед")
        self.btn_next.clicked.connect(self.next_track)
        controls_bar.addWidget(self.btn_next)

        self.btn_random_now = QPushButton("Случайный трек")
        self.btn_random_now.clicked.connect(self.play_random_track)
        controls_bar.addWidget(self.btn_random_now)

        self.btn_shuffle = QPushButton()
        self.btn_shuffle.clicked.connect(self.toggle_shuffle)
        controls_bar.addWidget(self.btn_shuffle)
        self.update_shuffle_button_text()

        self.btn_repeat = QPushButton()
        self.btn_repeat.clicked.connect(self.cycle_repeat_mode)
        controls_bar.addWidget(self.btn_repeat)
        self.update_repeat_button_text()

        vol_lbl = QLabel("Громкость:")
        controls_bar.addWidget(vol_lbl)

        self.vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(self.settings.get("volume", 70))
        self.vol_slider.setFixedWidth(90)
        self.vol_slider.valueChanged.connect(self.change_volume)
        controls_bar.addWidget(self.vol_slider)

        self.vol_val_lbl = QLabel(f"{self.settings.get('volume', 70)}%")
        controls_bar.addWidget(self.vol_val_lbl)

        player_layout.addLayout(controls_bar)

        routing_bar = QHBoxLayout()
        routing_bar.addWidget(QLabel("Вывод:"))

        self.btn_out_both = QPushButton("Динамики + Микрофон")
        self.btn_out_both.clicked.connect(lambda: self.set_output_mode("both"))
        routing_bar.addWidget(self.btn_out_both)

        self.btn_out_speakers = QPushButton("Только динамики")
        self.btn_out_speakers.clicked.connect(lambda: self.set_output_mode("speakers"))
        routing_bar.addWidget(self.btn_out_speakers)

        self.btn_out_mic = QPushButton("Только микрофон")
        self.btn_out_mic.clicked.connect(lambda: self.set_output_mode("mic"))
        routing_bar.addWidget(self.btn_out_mic)

        player_layout.addLayout(routing_bar)
        main_layout.addWidget(player_box)

    def apply_theme(self):
        c = self.settings.get("custom_colors", DEFAULT_THEMES["Cyber Cyan"])
        qss = f"""
            QMainWindow, QDialog {{ background-color: {c['bg']}; color: {c['text']}; }}
            QLabel {{ color: {c['text']}; font-size: 13px; }}
            #appTitle {{ font-size: 24px; font-weight: 700; color: {c['accent']}; }}
            #nowPlaying {{ font-size: 14px; font-weight: 600; color: {c['accent']}; }}
            #playerBox {{
                background-color: {c['card']};
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
                padding: 10px;
            }}
            QListWidget {{
                background-color: {c['card']};
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
                color: {c['text']};
                padding: 4px;
            }}
            QListWidget::item {{ padding: 8px; border-radius: 6px; }}
            QListWidget::item:selected {{ background-color: {c['accent']}; color: #000000; font-weight: 600; }}
            QPushButton {{
                background-color: {c['card']};
                color: {c['text']};
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
            }}
            QPushButton:hover {{ border-color: {c['accent']}; color: {c['accent']}; }}
            QLineEdit, QComboBox {{
                background-color: {c['card']};
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 6px;
                color: {c['text']};
                padding: 6px 10px;
            }}
            QSlider::groove:horizontal {{ height: 4px; background: rgba(255, 255, 255, 0.1); border-radius: 2px; }}
            QSlider::sub-page:horizontal {{ background: {c['accent']}; border-radius: 2px; }}
            QSlider::handle:horizontal {{ background: {c['accent']}; width: 12px; margin: -4px 0; border-radius: 6px; }}
            QMenu {{
                background-color: {c['card']};
                color: {c['text']};
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 6px;
                padding: 4px;
            }}
            QMenu::item:selected {{
                background-color: {c['accent']};
                color: #000000;
            }}
        """
        self.setStyleSheet(qss)
        self.update_output_buttons()

    def update_playlist_selector(self):
        self.playlist_combo.blockSignals(True)
        self.playlist_combo.clear()
        playlists = list(self.library_data.get("playlists", {}).keys())
        self.playlist_combo.addItems(playlists)
        current = self.library_data.get("current_playlist", "Основной")
        if current in playlists:
            self.playlist_combo.setCurrentText(current)
        elif playlists:
            self.playlist_combo.setCurrentIndex(0)
            self.library_data["current_playlist"] = playlists[0]
        self.playlist_combo.blockSignals(False)

    def on_playlist_changed(self, name):
        if not name:
            return
        self.library_data["current_playlist"] = name
        self.save_library()
        self.current_track_idx = -1
        self.refresh_track_list()

    def create_playlist(self):
        name, ok = QInputDialog.getText(self, "Новый плейлист", "Название плейлиста:")
        name = name.strip()
        if ok and name:
            playlists = self.library_data.setdefault("playlists", {})
            if name in playlists:
                QMessageBox.warning(self, "Ошибка", "Плейлист уже существует.")
                return
            playlists[name] = []
            self.library_data["current_playlist"] = name
            self.save_library()
            self.update_playlist_selector()
            self.refresh_track_list()

    def delete_current_playlist(self):
        name = self.current_playlist_name
        if name == "Основной":
            QMessageBox.warning(self, "Внимание", "Нельзя удалить 'Основной' плейлист.")
            return
        res = QMessageBox.question(
            self, "Удаление", f"Удалить плейлист '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if res == QMessageBox.StandardButton.Yes:
            self.library_data["playlists"].pop(name, None)
            self.library_data["current_playlist"] = "Основной"
            self.save_library()
            self.update_playlist_selector()
            self.refresh_track_list()

    def import_local_file(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Выберите аудио", "", "Аудио (*.mp3 *.wav *.ogg *.m4a *.flac)"
        )
        for f in files:
            p = Path(f)
            dest = TRACKS_DIR / p.name
            try:
                if not dest.exists():
                    shutil.copy2(f, dest)
                self.current_tracks.append({"title": p.stem, "path": str(dest)})
            except Exception as e:
                print(f"Ошибка копирования: {e}")

        self.save_library()
        self.refresh_track_list()

    def import_url(self):
        text = self.url_input.text().strip()
        if not text:
            return
        self.btn_add_url.setEnabled(False)
        self.progress_bar.setVisible(True)

        self.worker = DownloadWorker(text)
        self.worker.finished_sig.connect(self.on_download_finished)
        self.worker.start()

    def on_download_finished(self, success, result):
        self.btn_add_url.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.url_input.clear()

        if success:
            p = Path(result)
            self.current_tracks.append({"title": p.stem, "path": str(p)})
            self.save_library()
            self.refresh_track_list()
            QMessageBox.information(self, "Готово", f"Трек загружен:\n{p.stem}")
        else:
            QMessageBox.warning(self, "Ошибка", f"Не удалось загрузить:\n{result}")

    def refresh_track_list(self):
        self.track_list_widget.clear()
        for t in self.current_tracks:
            self.track_list_widget.addItem(t["title"])

    def show_context_menu(self, pos):
        item = self.track_list_widget.itemAt(pos)
        if not item:
            return
        row = self.track_list_widget.row(item)
        menu = QMenu(self)

        play_act = menu.addAction("Воспроизвести")
        add_to_pl_menu = menu.addMenu("Скопировать в плейлист")
        for pl_name in self.library_data.get("playlists", {}).keys():
            if pl_name != self.current_playlist_name:
                act = add_to_pl_menu.addAction(pl_name)
                act.triggered.connect(lambda ch, p=pl_name, r=row: self.copy_track_to_pl(r, p))

        del_from_pl = menu.addAction("Удалить из плейлиста")
        del_file = menu.addAction("Удалить файл с диска")

        action = menu.exec(self.track_list_widget.mapToGlobal(pos))
        if action == play_act:
            self.play_track_by_index(row)
        elif action == del_from_pl:
            self.remove_track_from_current_pl(row)
        elif action == del_file:
            self.delete_track_file(row)

    def copy_track_to_pl(self, row, target_pl):
        track = self.current_tracks[row]
        self.library_data["playlists"][target_pl].append(track)
        self.save_library()
        QMessageBox.information(self, "Успех", f"Трек добавлен в '{target_pl}'.")

    def remove_track_from_current_pl(self, row):
        if row == self.current_track_idx:
            self.stop_playback()
        self.current_tracks.pop(row)
        self.save_library()
        self.refresh_track_list()

    def delete_track_file(self, row):
        if row == self.current_track_idx:
            self.stop_playback()
        track = self.current_tracks.pop(row)
        try:
            os.remove(track["path"])
        except Exception:
            pass
        self.save_library()
        self.refresh_track_list()

    def play_selected_track(self, item):
        idx = self.track_list_widget.row(item)
        self.play_track_by_index(idx)

    def play_track_by_index(self, idx):
        tracks = self.current_tracks
        if 0 <= idx < len(tracks):
            self.current_track_idx = idx
            track = tracks[idx]
            url = QUrl.fromLocalFile(track["path"])

            self.player.setSource(url)
            self.player.play()

            if self.is_mic_active():
                self.mic_player.setSource(url)
                self.mic_player.play()

            self.apply_output_mode()

            self.btn_play.setText("Пауза")
            self.now_playing_lbl.setText(track["title"])
            self.track_list_widget.setCurrentRow(idx)
            self.discord.update_status(track["title"], is_playing=True)

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            if self.is_mic_active():
                self.mic_player.pause()
            self.btn_play.setText("Воспроизвести")
            if self.current_track_idx != -1:
                self.discord.update_status(self.current_tracks[self.current_track_idx]["title"], is_playing=False)
        else:
            if self.current_track_idx == -1 and len(self.current_tracks) > 0:
                self.play_track_by_index(0)
            else:
                self.player.play()
                if self.is_mic_active():
                    self.mic_player.play()
                self.apply_output_mode()
                self.btn_play.setText("Пауза")
                if self.current_track_idx != -1:
                    self.discord.update_status(self.current_tracks[self.current_track_idx]["title"], is_playing=True)

    def stop_playback(self):
        self.player.stop()
        self.mic_player.stop()
        self.now_playing_lbl.setText("Нет воспроизводимого трека")
        self.btn_play.setText("Воспроизвести")
        self.current_track_idx = -1
        self.discord.clear()

    def prev_track(self):
        tracks = self.current_tracks
        if not tracks:
            return
        if self.settings.get("shuffle", False):
            self.play_random_track()
        else:
            new_idx = (self.current_track_idx - 1) % len(tracks)
            self.play_track_by_index(new_idx)

    def next_track(self):
        tracks = self.current_tracks
        if not tracks:
            return
        if self.settings.get("shuffle", False):
            self.play_random_track()
        else:
            new_idx = (self.current_track_idx + 1) % len(tracks)
            self.play_track_by_index(new_idx)

    def play_random_track(self):
        tracks = self.current_tracks
        if not tracks:
            return
        if len(tracks) == 1:
            self.play_track_by_index(0)
            return
        indices = [i for i in range(len(tracks)) if i != self.current_track_idx]
        new_idx = random.choice(indices)
        self.play_track_by_index(new_idx)

    def toggle_shuffle(self):
        self.settings["shuffle"] = not self.settings.get("shuffle", False)
        self.update_shuffle_button_text()
        self.save_settings()

    def update_shuffle_button_text(self):
        if self.settings.get("shuffle", False):
            self.btn_shuffle.setText("Рандом: Вкл")
        else:
            self.btn_shuffle.setText("Рандом: Выкл")

    def cycle_repeat_mode(self):
        current = self.settings.get("repeat_mode", "all")
        modes = ["all", "one", "none"]
        next_mode = modes[(modes.index(current) + 1) % len(modes)]
        self.settings["repeat_mode"] = next_mode
        self.update_repeat_button_text()
        self.save_settings()

    def update_repeat_button_text(self):
        mode = self.settings.get("repeat_mode", "all")
        if mode == "all":
            self.btn_repeat.setText("Повтор: Все")
        elif mode == "one":
            self.btn_repeat.setText("Повтор: Трек")
        else:
            self.btn_repeat.setText("Повтор: Выкл")

    def on_media_status_changed(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            tracks = self.current_tracks
            if not tracks:
                return

            repeat_mode = self.settings.get("repeat_mode", "all")
            if repeat_mode == "one":
                self.play_track_by_index(self.current_track_idx)
                return

            if self.settings.get("shuffle", False):
                self.play_random_track()
                return

            if self.current_track_idx + 1 < len(tracks):
                self.play_track_by_index(self.current_track_idx + 1)
            elif repeat_mode == "all":
                self.play_track_by_index(0)
            else:
                self.stop_playback()

    def change_volume(self, val):
        self.audio_output.setVolume(val / 100.0)
        self.vol_val_lbl.setText(f"{val}%")
        self.settings["volume"] = val
        self.save_settings()

    def set_position(self, pos):
        self.player.setPosition(pos)
        if self.is_mic_active():
            self.mic_player.setPosition(pos)

    def on_position_changed(self, pos):
        if not self.seek_slider.isSliderDown():
            self.seek_slider.setValue(pos)
        dur = self.player.duration()
        self.time_lbl.setText(f"{self.format_time(pos)} / {self.format_time(dur)}")

    def on_duration_changed(self, dur):
        self.seek_slider.setRange(0, dur)

    def format_time(self, ms):
        s = ms // 1000
        m, s = divmod(s, 60)
        return f"{m}:{s:02d}"

    def open_settings(self):
        dlg = SettingsDialog(self)
        dlg.exec()

    def closeEvent(self, event):
        if KEYBOARD_AVAILABLE:
            try:
                keyboard.unhook_all()
            except Exception:
                pass
        self.discord.clear()
        self.player.stop()
        self.mic_player.stop()
        event.accept()


def main():
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("kalel.music.app")
    except Exception:
        pass

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()