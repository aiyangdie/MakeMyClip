# -*- coding: utf-8 -*-
"""视频预览播放器：用 OpenCV 逐帧解码 + QTimer 驱动。

为什么不用 QMediaPlayer：
- Windows 上 Qt 多媒体的编解码器常缺失，MOV/HEVC 容易黑屏；
- OpenCV(带 FFmpeg) 解码更稳，且天然支持逐帧定位，符合任务书要求。
原始素材仍只读——播放只通过 media.preview_link 的代理路径读取。
"""
import cv2
from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QFrame,
)

from .. import media


class VideoPlayer(QObject):
    """纯逻辑播放器，负责解码与计时，通过 frame_ready 把画面交给界面。"""
    frame_ready = Signal(object)      # QImage
    position_changed = Signal(int)    # ms
    duration_changed = Signal(int)
    playback_state = Signal(bool)     # 是否播放中

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cap = None
        self.path = None
        self.duration_ms = 0
        self.fps = 30.0
        self.playing = False
        self._clip_start = 0
        self._clip_end = 0            # 0 表示整段
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self._tick)

    def open(self, path, start_ms=0, end_ms=0):
        self.close()
        proxy = media.preview_link(path)
        self.cap = cv2.VideoCapture(proxy)
        if not self.cap.isOpened():
            self.path = None
            return False
        self.path = path
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        frames = self.cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
        self.duration_ms = int(frames / self.fps * 1000) if self.fps else 0
        self._clip_start = max(0, start_ms)
        self._clip_end = end_ms if end_ms and end_ms > self._clip_start else self.duration_ms
        self.duration_changed.emit(self._clip_end - self._clip_start)
        self.seek(0)
        return True

    def close(self):
        self.timer.stop()
        self.playing = False
        self.playback_state.emit(False)
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        self.path = None

    def play(self):
        if self.cap is None:
            return
        if self._current_ms() >= self._clip_end - 50:
            self.seek(0)
        self.playing = True
        self.playback_state.emit(True)
        self.timer.start()

    def pause(self):
        self.playing = False
        self.timer.stop()
        self.playback_state.emit(False)

    def toggle(self):
        self.pause() if self.playing else self.play()

    def _current_ms(self):
        if self.cap is None:
            return 0
        return int(self.cap.get(cv2.CAP_PROP_POS_MSEC) or 0)

    def seek(self, ms):
        """ms 为相对于片段起点的毫秒。"""
        if self.cap is None:
            return
        target = self._clip_start + max(0, ms)
        self.cap.set(cv2.CAP_PROP_POS_MSEC, target)
        self.position_changed.emit(max(0, ms))
        self._grab()

    def step(self, delta_frames):
        """逐帧：正/负一帧。OpenCV 后退需重新定位。"""
        if self.cap is None:
            return
        cur_frame = self.cap.get(cv2.CAP_PROP_POS_FRAMES) or 0
        new_frame = int(cur_frame) + delta_frames
        if new_frame < 0:
            new_frame = 0
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, new_frame)
        actual_ms = int(self.cap.get(cv2.CAP_PROP_POS_MSEC) or 0) - self._clip_start
        self.position_changed.emit(max(0, actual_ms))
        self._grab()

    def _tick(self):
        if self.cap is None:
            return
        ms = self._current_ms()
        if ms >= self._clip_end:
            self.pause()
            return
        self.position_changed.emit(max(0, ms - self._clip_start))
        self._grab()

    def _grab(self):
        if self.cap is None:
            return
        ok, frame = self.cap.read()
        if not ok:
            self.pause()
            return
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        self.frame_ready.emit(img.copy())


class PlayerWidget(QWidget):
    """带画面与控制条的完整预览组件。"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.player = VideoPlayer(self)
        self._build_ui()
        self.player.frame_ready.connect(self._show_frame)
        self.player.position_changed.connect(self._on_pos)
        self.player.duration_changed.connect(self._on_duration)
        self.player.playback_state.connect(self._on_state)
        self.slider.sliderMoved.connect(self.player.seek)
        self.btn_play.clicked.connect(self.player.toggle)
        self.btn_prev.clicked.connect(lambda: self.player.step(-1))
        self.btn_next.clicked.connect(lambda: self.player.step(1))

    def _build_ui(self):
        v = QVBoxLayout(self)
        self.screen = QLabel("未加载视频")
        self.screen.setAlignment(Qt.AlignCenter)
        self.screen.setStyleSheet("background:#111;color:#888;font-size:14px;")
        self.screen.setMinimumHeight(260)
        self.screen.setScaledContents(True)
        v.addWidget(self.screen, 1)

        ctrl = QHBoxLayout()
        self.btn_prev = QPushButton("◀ 帧")
        self.btn_play = QPushButton("▶ 播放")
        self.btn_next = QPushButton("帧 ▶")
        for b in (self.btn_prev, self.btn_play, self.btn_next):
            b.setFixedWidth(64)
            ctrl.addWidget(b)
        self.slider = QSlider(Qt.Horizontal)
        ctrl.addWidget(self.slider, 1)
        self.lbl_time = QLabel("00:00 / 00:00")
        self.lbl_time.setFixedWidth(110)
        ctrl.addWidget(self.lbl_time)
        v.addLayout(ctrl)

    def open(self, path, start_ms=0, end_ms=0):
        return self.player.open(path, start_ms, end_ms)

    def stop(self):
        self.player.close()
        self.screen.setText("未加载视频")
        self.slider.setValue(0)
        self.lbl_time.setText("00:00 / 00:00")

    def _show_frame(self, img):
        self.screen.setPixmap(QPixmap.fromImage(img))

    def _on_pos(self, ms):
        self.slider.blockSignals(True)
        self.slider.setValue(ms)
        self.slider.blockSignals(False)
        self._update_time()

    def _on_duration(self, ms):
        self.slider.setMaximum(max(1, ms))
        self._update_time()

    def _on_state(self, playing):
        self.btn_play.setText("⏸ 暂停" if playing else "▶ 播放")

    def _update_time(self):
        dur = self.slider.maximum()
        self.lbl_time.setText(f"{media.format_duration(self.slider.value())} / {media.format_duration(dur)}")
