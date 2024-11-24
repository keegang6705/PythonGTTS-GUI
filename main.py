import os
import sys
import json
import time
from pydub import AudioSegment
from pathlib import Path
from gtts import gTTS
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QLineEdit,
                             QPushButton, QComboBox, QLabel, QHBoxLayout,
                             QListWidget, QDialog, QDialogButtonBox, QMessageBox,QSlider)
from PySide6.QtGui import QPalette, QColor
from PySide6.QtCore import Qt, QUrl, QTimer
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaDevices


class QuickMessageDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Quick Message")
        self.setModal(True)

        layout = QVBoxLayout(self)

        self.message_input = QLineEdit()
        self.message_input.setPlaceholderText("Enter quick message...")
        layout.addWidget(self.message_input)

        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)


class TTSApp(QWidget):
    def __init__(self):
        super().__init__()
        self.app_dir = Path(__file__).parent
        self.config_path = self.app_dir / 'config.json'
        self.audio_path = self.app_dir / 'tmp'
        self.media_player = None
        self.cleanup_timer = QTimer()
        self.cleanup_timer.timeout.connect(self.delayed_cleanup)
        self.load_config()
        self.init_ui()
        self.setup_audio()
        self.apply_dark_theme()

    def load_config(self):
        default_config = {
            "language": "English",
            "playback_speed":100,
            "quick_messages": [
                "Hello, how are you?",
                "Thank you",
                "Goodbye"
            ]
        }

        try:
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
            else:
                self.config = default_config
                self.save_config()
        except Exception as e:
            print(f"Error loading config: {str(e)}")
            self.config = default_config
            self.save_config()

    def save_config(self):
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving config: {str(e)}")

    def init_ui(self):
        self.setWindowTitle("TTS Application")
        self.setGeometry(100, 100, 800, 600)

        main_layout = QHBoxLayout()
        left_panel = QVBoxLayout()
        right_panel = QVBoxLayout()

        # Left Panel - Main Controls
        # Text input
        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText("Enter text here...")
        self.text_input.setFixedHeight(50)
        self.text_input.setStyleSheet(self.get_input_style())
        left_panel.addWidget(self.text_input)

        # Language selection
        self.language_selection = QComboBox()
        self.language_selection.addItems(["English", "Thai"])
        self.language_selection.setCurrentText(self.config["language"])
        self.language_selection.setStyleSheet(self.get_combobox_style())
        self.language_selection.currentTextChanged.connect(self.save_settings)
        left_panel.addWidget(QLabel("Language:", styleSheet="color: white;"))
        left_panel.addWidget(self.language_selection)

        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setRange(100, 200)
        self.speed_slider.setValue(self.config["playback_speed"])
        self.speed_slider.setTickInterval(10)
        self.speed_slider.setTickPosition(QSlider.TicksBelow)
        self.speed_slider.valueChanged.connect(self.update_speed)
        self.speed_slider.setStyleSheet("QSlider { background-color: #333333; }")
        left_panel.addWidget(QLabel("Speech Speed:", styleSheet="color: white;"))
        left_panel.addWidget(self.speed_slider)

        # Audio device selection
        left_panel.addWidget(QLabel("Output Device:", styleSheet="color: white;"))
        self.audio_output_selection = QComboBox()
        self.audio_output_selection.setStyleSheet(self.get_combobox_style())
        left_panel.addWidget(self.audio_output_selection)

        # Speak button
        self.speak_button = QPushButton("Speak")
        self.speak_button.setFixedHeight(50)
        self.speak_button.setStyleSheet(self.get_button_style())
        self.speak_button.clicked.connect(self.speak_text)
        left_panel.addWidget(self.speak_button)

        self.status_label = QLabel("Playback status: Not started")
        self.status_label.setStyleSheet("color: white; font-size: 14px;")
        left_panel.addWidget(self.status_label)

        left_panel.addStretch()

        # Right Panel - Quick Messages
        right_panel.addWidget(QLabel("Quick Messages:",styleSheet="color: white; font-size: 16px;"))

        # Quick messages list
        self.quick_messages_list = QListWidget()
        self.quick_messages_list.setStyleSheet("""
            QListWidget {
                background-color: #333333;
                font-size: 16px;
                color: white;
                border: 1px solid #555555;
                border-radius: 5px;
            }
            QListWidget::item {
                padding: 5px;
            }
            QListWidget::item:selected {
                background-color: #4CAF50;
            }
        """)
        self.quick_messages_list.addItems(self.config["quick_messages"])
        self.quick_messages_list.itemDoubleClicked.connect(self.use_quick_message)
        right_panel.addWidget(self.quick_messages_list)

        # Quick message buttons
        quick_msg_buttons = QHBoxLayout()

        add_msg_btn = QPushButton("Add Message")
        add_msg_btn.setStyleSheet(self.get_button_style())
        add_msg_btn.clicked.connect(self.add_quick_message)

        remove_msg_btn = QPushButton("Remove Message")
        remove_msg_btn.setStyleSheet(self.get_button_style(color="#e74c3c"))
        remove_msg_btn.clicked.connect(self.remove_quick_message)

        quick_msg_buttons.addWidget(add_msg_btn)
        quick_msg_buttons.addWidget(remove_msg_btn)
        right_panel.addLayout(quick_msg_buttons)

        # Add panels to main layout
        main_layout.addLayout(left_panel, 1)
        main_layout.addLayout(right_panel, 1)
        self.setLayout(main_layout)

    def setup_audio(self):
        self.audio_output = QAudioOutput()
        self.media_player = QMediaPlayer()
        self.media_player.setAudioOutput(self.audio_output)

        # Connect playback state changed signal
        self.media_player.playbackStateChanged.connect(self.on_playback_state_changed)

        # Get available audio output devices
        audio_devices = QMediaDevices.audioOutputs()
        for device in audio_devices:
            self.audio_output_selection.addItem(device.description(), device)

        self.audio_output_selection.currentIndexChanged.connect(self.set_output_device)

        # Set default device
        if self.audio_output_selection.count() > 0:
            self.set_output_device(0)

    def delayed_cleanup(self):
        try:
            if self.audio_path and self.audio_path.exists():
                if self.audio_path.is_dir():
                    # Iterate through all files in the directory and delete them
                    for file in os.listdir(self.audio_path):
                        file_path = os.path.join(self.audio_path, file)
                        try:
                            if os.path.isfile(file_path):
                                os.remove(file_path)
                                print(f"Deleted file: {file_path}")
                        except:
                            continue
                else:
                    # If it's a file, just delete it
                    os.remove(str(self.audio_path))
                    print(f"Deleted temporary file: {self.audio_path}")
        except Exception as e:
            print(f"Error during cleanup: {str(e)}")

    def on_playback_state_changed(self, state):
        if state == QMediaPlayer.StoppedState:
            self.cleanup_timer.start(100)
            self.status_label.setText("Playback status: Finished")  # Update status
        elif state == QMediaPlayer.PlayingState:
            self.status_label.setText("Playback status: Playing...")  # Update status when playing
        elif state == QMediaPlayer.PausedState:
            self.status_label.setText("Playback status: Paused")  # Update status if paused

    def get_speed_multiplier(self):
        return self.speed_slider.value() / 100.0 
    def speak_text(self):
        try:
            text = self.text_input.text()
            if not text:
                return

            lang = 'en' if self.language_selection.currentText() == "English" else 'th'
            
            # Stop any currently playing audio
            if self.media_player:
                self.media_player.stop()

            # Create tmp folder if it doesn't exist
            tmp_folder = self.app_dir / 'tmp'
            tmp_folder.mkdir(exist_ok=True)

            temp_name = f'temp_{int(time.time())}.mp3'
            temp_path = tmp_folder / temp_name

            # Generate TTS and save to the temporary file
            tts = gTTS(text=text, lang=lang, slow=False)
            tts.save(str(temp_path))

            speed_multiplier = self.get_speed_multiplier()
            if speed_multiplier > 1.0:
                sound = AudioSegment.from_mp3(str(temp_path))
                sound = sound.speedup(playback_speed=speed_multiplier)

                adjusted_temp_name = f'adjusted_{temp_name}'
                adjusted_temp_path = tmp_folder / adjusted_temp_name
                sound.export(str(adjusted_temp_path), format="mp3")

                self.media_player.setSource(QUrl.fromLocalFile(str(adjusted_temp_path)))
                self.media_player.play()
            else:
                self.media_player.setSource(QUrl.fromLocalFile(str(temp_path)))
                self.media_player.play()

        except Exception as e:
            QMessageBox.warning(self, "Error", f"Error while speaking: {str(e)}")

    def set_output_device(self, index):
        if index >= 0:
            device = self.audio_output_selection.itemData(index)
            self.audio_output.setDevice(device)

    def add_quick_message(self):
        dialog = QuickMessageDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            message = dialog.message_input.text().strip()
            if message:
                self.quick_messages_list.addItem(message)
                self.save_settings()

    def remove_quick_message(self):
        current_item = self.quick_messages_list.currentItem()
        if current_item:
            self.quick_messages_list.takeItem(self.quick_messages_list.row(current_item))
            self.save_settings()

    def use_quick_message(self, item):
        self.text_input.setText(item.text())
        self.speak_text()
    def update_speed(self, value):
        self.config["playback_speed"] = value
        self.save_config() 

    def save_settings(self):
        self.config.update({
            "language": self.language_selection.currentText(),
            "quick_messages": [self.quick_messages_list.item(i).text() 
                             for i in range(self.quick_messages_list.count())]
        })
        self.save_config()

    def get_input_style(self):
        return """
            QLineEdit {
                background-color: #333333;
                color: white;
                font-size: 18px;
                padding: 5px;
                border: 1px solid #555555;
                border-radius: 5px;
            }
        """

    def get_combobox_style(self):
        return """
            QComboBox {
                background-color: #555555;
                color: white;
                font-size: 16px;
                padding: 5px;
                border: 1px solid #666666;
                border-radius: 5px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid white;
                margin-right: 5px;
            }
            QComboBox QAbstractItemView {
                background-color: #555555;
                color: white;
                selection-background-color: #666666;
            }
        """

    def get_button_style(self, color="#4CAF50"):
        return f"""
            QPushButton {{
                background-color: {color};
                color: white;
                font-size: 14px;
                border: none;
                border-radius: 5px;
                padding: 8px;
            }}
            QPushButton:hover {{
                background-color: {self.adjust_color(color, -10)};
            }}
            QPushButton:pressed {{
                background-color: {self.adjust_color(color, -20)};
            }}
        """

    def adjust_color(self, hex_color, factor):
        hex_color = hex_color.lstrip('#')
        r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        r = max(0, min(255, r + factor))
        g = max(0, min(255, g + factor))
        b = max(0, min(255, b + factor))
        return f"#{int(r):02x}{int(g):02x}{int(b):02x}"

    def apply_dark_theme(self):
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(30, 30, 30))
        palette.setColor(QPalette.WindowText, Qt.white)
        palette.setColor(QPalette.Base, QColor(40, 40, 40))
        palette.setColor(QPalette.AlternateBase, QColor(30, 30, 30))
        palette.setColor(QPalette.ToolTipBase, Qt.white)
        palette.setColor(QPalette.ToolTipText, Qt.white)
        palette.setColor(QPalette.Text, Qt.white)
        palette.setColor(QPalette.Button, QColor(45, 45, 45))
        palette.setColor(QPalette.ButtonText, Qt.white)
        palette.setColor(QPalette.BrightText, Qt.red)
        palette.setColor(QPalette.Highlight, QColor(80, 80, 80))
        palette.setColor(QPalette.HighlightedText, Qt.white)
        self.setPalette(palette)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TTSApp()
    window.show()
    sys.exit(app.exec())