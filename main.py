import sys
import os
import json
import shutil
import re
import urllib.request
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl, pyqtSignal, QThread
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSlider, QListWidget, QListWidgetItem,
    QFileDialog, QDialog, QLineEdit, QComboBox, QColorDialog,
    QMessageBox, QFrame, QProgressBar
)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

# ========================================================
# ТВОЙ DISCORD APPLICATION ID:
DISCORD_CLIENT_ID = "1552402566283796601"
# ========================================================

# Discord Rich Presence
try:
    from pypresence import Presence
    DISCORD_AVAILABLE = True
except ImportError:
    DISCORD_AVAILABLE = False

# Папки приложения
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
    "volume": 70
}


def get_app_icon():
    icon_path = Path("123.ico")
    if icon_path.exists():
        return QIcon(str(icon_path))
    pixmap = QPixmap(32, 32)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setBrush(QColor("#38bdf8"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(2, 2, 28, 28, 8, 8)
    painter.end()
    return QIcon(pixmap)


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
        self.setFixedSize(480, 440)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        layout.addWidget(QLabel("Предустановленные темы:"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(list(DEFAULT_THEMES.keys()) + ["Пользовательская"])
        self.theme_combo.setCurrentText(self.main_app.settings.get("current_theme", "Cyber Cyan"))
        self.theme_combo.currentTextChanged.connect(self.on_theme_select)
        layout.addWidget(self.theme_combo)

        layout.addWidget(QLabel("Кастомизация цветов:"))
        colors_grid = QVBoxLayout()
        for key, name in [("bg", "Цвет фона"), ("card", "Цвет карточек"), ("accent", "Акцентный цвет"), ("text", "Цвет текста")]:
            btn = QPushButton(name)
            btn.clicked.connect(lambda checked, k=key: self.pick_color(k))
            colors_grid.addWidget(btn)
        layout.addLayout(colors_grid)

        layout.addWidget(QLabel("Резервное копирование настроек:"))
        backup_box = QHBoxLayout()
        btn_export = QPushButton("Экспорт настроек")
        btn_export.clicked.connect(self.export_settings)
        backup_box.addWidget(btn_export)

        btn_import = QPushButton("Импорт настроек")
        btn_import.clicked.connect(self.import_settings)
        backup_box.addWidget(btn_import)
        layout.addLayout(backup_box)

        btn_save = QPushButton("Закрыть")
        btn_save.clicked.connect(self.save_and_close)
        layout.addWidget(btn_save)

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
            QMessageBox.information(self, "Успех", "Настройки сохранены в файл.")

    def import_settings(self):
        path, _ = QFileDialog.getOpenFileName(self, "Импорт настроек", "", "JSON (*.json)")
        if path:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    new_settings = json.load(f)
                    self.main_app.settings.update(new_settings)
                self.main_app.apply_theme()
                self.main_app.save_settings()
                self.theme_combo.setCurrentText(self.main_app.settings.get("current_theme", "Пользовательская"))
                QMessageBox.information(self, "Успех", "Настройки успешно загружены.")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Ошибка чтения: {e}")

    def save_and_close(self):
        self.main_app.save_settings()
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("kalel music")
        self.setWindowIcon(get_app_icon())
        self.resize(780, 700)

        self.tracks = []
        self.current_track_idx = -1
        self.settings = self.load_settings()

        # Инициализация Discord RPC с твоим ID
        self.discord = DiscordManager(DISCORD_CLIENT_ID)
        self.discord.connect()

        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(self.settings.get("volume", 70) / 100.0)

        self.init_ui()
        self.apply_theme()
        self.load_library()

        self.player.positionChanged.connect(self.on_position_changed)
        self.player.durationChanged.connect(self.on_duration_changed)

    def load_settings(self):
        if SETTINGS_FILE.exists():
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                pass
        return DEFAULT_SETTINGS.copy()

    def save_settings(self):
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(self.settings, f, indent=4)

    def load_library(self):
        if LIBRARY_FILE.exists():
            try:
                with open(LIBRARY_FILE, "r", encoding="utf-8") as f:
                    self.tracks = json.load(f)
            except:
                self.tracks = []
        self.refresh_track_list()

    def save_library(self):
        with open(LIBRARY_FILE, "w", encoding="utf-8") as f:
            json.dump(self.tracks, f, indent=4)

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(16)

        header = QHBoxLayout()
        self.title_lbl = QLabel("kalel")
        self.title_lbl.setObjectName("appTitle")
        header.addWidget(self.title_lbl)

        header.addStretch()

        self.btn_settings = QPushButton("Настройки")
        self.btn_settings.clicked.connect(self.open_settings)
        header.addWidget(self.btn_settings)

        main_layout.addLayout(header)

        actions_bar = QHBoxLayout()
        self.btn_add_file = QPushButton("Добавить MP3")
        self.btn_add_file.clicked.connect(self.import_local_file)
        actions_bar.addWidget(self.btn_add_file)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Ссылка / iframe Spotify, YouTube, SoundCloud...")
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
        main_layout.addWidget(self.track_list_widget)

        player_box = QFrame()
        player_box.setObjectName("playerBox")
        player_layout = QVBoxLayout(player_box)
        player_layout.setSpacing(10)

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

        self.btn_delete = QPushButton("Удалить")
        self.btn_delete.clicked.connect(self.delete_track)
        controls_bar.addWidget(self.btn_delete)

        controls_bar.addSpacing(20)

        vol_lbl = QLabel("Громкость:")
        controls_bar.addWidget(vol_lbl)

        self.vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(self.settings.get("volume", 70))
        self.vol_slider.setFixedWidth(120)
        self.vol_slider.valueChanged.connect(self.change_volume)
        controls_bar.addWidget(self.vol_slider)

        self.vol_val_lbl = QLabel(f"{self.settings.get('volume', 70)}%")
        controls_bar.addWidget(self.vol_val_lbl)

        player_layout.addLayout(controls_bar)
        main_layout.addWidget(player_box)

    def apply_theme(self):
        c = self.settings.get("custom_colors", DEFAULT_THEMES["Cyber Cyan"])
        qss = f"""
            QMainWindow, QDialog {{ background-color: {c['bg']}; color: {c['text']}; }}
            QLabel {{ color: {c['text']}; font-size: 13px; }}
            #appTitle {{ font-size: 28px; font-weight: 700; color: {c['text']}; }}
            #nowPlaying {{ font-size: 14px; font-weight: 600; color: {c['accent']}; }}
            #playerBox {{
                background-color: {c['card']};
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 16px;
                padding: 14px;
            }}
            QListWidget {{
                background-color: {c['card']};
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 16px;
                color: {c['text']};
                padding: 8px;
            }}
            QListWidget::item {{ padding: 10px; border-radius: 8px; }}
            QListWidget::item:selected {{ background-color: {c['accent']}; color: #000000; font-weight: 600; }}
            QPushButton {{
                background-color: {c['card']};
                color: {c['text']};
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 8px 14px;
                font-size: 13px;
                font-weight: 500;
            }}
            QPushButton:hover {{ border-color: {c['accent']}; color: {c['accent']}; }}
            QLineEdit, QComboBox {{
                background-color: {c['card']};
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                color: {c['text']};
                padding: 8px 12px;
            }}
            QSlider::groove:horizontal {{ height: 4px; background: rgba(255, 255, 255, 0.1); border-radius: 2px; }}
            QSlider::sub-page:horizontal {{ background: {c['accent']}; border-radius: 2px; }}
            QSlider::handle:horizontal {{ background: {c['accent']}; width: 12px; margin-top: -4px; margin-bottom: -4px; border-radius: 6px; }}
        """
        self.setStyleSheet(qss)

    def import_local_file(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Выберите аудиофайлы", "", "Аудио (*.mp3 *.wav *.ogg *.m4a *.flac)"
        )
        for f in files:
            p = Path(f)
            dest = TRACKS_DIR / p.name
            try:
                shutil.copy2(f, dest)
                self.tracks.append({"title": p.stem, "path": str(dest)})
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
            self.tracks.append({"title": p.stem, "path": str(p)})
            self.save_library()
            self.refresh_track_list()
            QMessageBox.information(self, "Готово", f"Трек загружен:\n{p.stem}")
        else:
            QMessageBox.warning(self, "Ошибка скачивания", f"Не удалось загрузить:\n{result}")

    def refresh_track_list(self):
        self.track_list_widget.clear()
        for t in self.tracks:
            self.track_list_widget.addItem(t["title"])

    def play_selected_track(self, item):
        idx = self.track_list_widget.row(item)
        self.play_track_by_index(idx)

    def play_track_by_index(self, idx):
        if 0 <= idx < len(self.tracks):
            self.current_track_idx = idx
            track = self.tracks[idx]
            self.player.setSource(QUrl.fromLocalFile(track["path"]))
            self.player.play()
            self.btn_play.setText("Пауза")
            self.now_playing_lbl.setText(track["title"])
            self.track_list_widget.setCurrentRow(idx)
            self.discord.update_status(track["title"], is_playing=True)

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.btn_play.setText("Воспроизвести")
            if self.current_track_idx != -1:
                self.discord.update_status(self.tracks[self.current_track_idx]["title"], is_playing=False)
        else:
            if self.current_track_idx == -1 and len(self.tracks) > 0:
                self.play_track_by_index(0)
            else:
                self.player.play()
                self.btn_play.setText("Пауза")
                if self.current_track_idx != -1:
                    self.discord.update_status(self.tracks[self.current_track_idx]["title"], is_playing=True)

    def prev_track(self):
        if self.tracks:
            new_idx = (self.current_track_idx - 1) % len(self.tracks)
            self.play_track_by_index(new_idx)

    def next_track(self):
        if self.tracks:
            new_idx = (self.current_track_idx + 1) % len(self.tracks)
            self.play_track_by_index(new_idx)

    def delete_track(self):
        row = self.track_list_widget.currentRow()
        if row >= 0:
            if row == self.current_track_idx:
                self.player.stop()
                self.now_playing_lbl.setText("Нет воспроизводимого трека")
                self.btn_play.setText("Воспроизвести")
                self.current_track_idx = -1
                self.discord.clear()

            track = self.tracks.pop(row)
            try:
                os.remove(track["path"])
            except:
                pass
            self.save_library()
            self.refresh_track_list()

    def change_volume(self, val):
        self.audio_output.setVolume(val / 100.0)
        self.vol_val_lbl.setText(f"{val}%")
        self.settings["volume"] = val
        self.save_settings()

    def set_position(self, pos):
        self.player.setPosition(pos)

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
        self.discord.clear()
        self.player.stop()
        event.accept()


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()