# -*- coding: utf-8 -*-
"""阶段 B · 页面一：素材与商品信息

功能范围（任务书三·页面一）：
  - 视频/图片导入（图片支持由 workshop_data.image_support 补齐）
  - 缩略图 / 文件名 / 时长 / 分辨率 / 五态
  - 多选删除、重新导入、分组筛选、重复素材提示
  - 分析进度、异常素材、待确认事项
  - 点击素材看预览与可用分析信息
  - 商品名称/卖点、比例/时长/字幕/BGM/配音设置
  - 开始分析（复用既有 AnalyzeWorker，不重写分析逻辑）

诚实边界：
  - 图片素材当前只做导入与展示，**不做自动分析**（渲染链尚不支持静帧，属阶段 D）。
  - 顶栏已常驻"基础算法测量，非 AI 理解"。
"""
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPixmap, QFont
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame,
                               QPushButton, QScrollArea, QGridLayout, QComboBox,
                               QLineEdit, QTextEdit, QSpinBox, QCheckBox,
                               QFileDialog, QMessageBox, QSizePolicy, QProgressBar,
                               QDialog, QListWidget, QListWidgetItem, QDialogButtonBox)

from .. import design_tokens as dt
from ...workshop_data import bridge, image_support as img
from ...workshop_data import models as M
from .widgets import AssetCard, StatusChip, StatChip, GroupRow, EmptyState, TinyTag

# 复用既有分析线程（只 import，不改它）
from ...workers import AnalyzeWorker


class WorkspacePage(QWidget):
    """素材与商品信息页。"""

    request_open_storyboard = Signal()
    status_message = Signal(str)

    def __init__(self, dark=False, parent=None):
        super().__init__(parent)
        self._dark = dark
        self.db = None
        self.project = None
        self._group = "全部"
        self._cards = {}
        self._selected = set()
        self._analyze_worker = None

        # 【阶段B修复 20261121 增补】当前项目路径；导入/删除后据此重新读取项目清单
        self.db_path = None

        self._build()
        self.refresh_all()

    # ================= 界面 =================
    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_side())
        root.addWidget(self._build_main(), 1)
        root.addWidget(self._build_info())

    # ---------- 左：分组 ----------
    def _build_side(self):
        self.side = QFrame()
        self.side.setFixedWidth(180)
        lay = QVBoxLayout(self.side)
        lay.setContentsMargins(10, 12, 10, 10)
        lay.setSpacing(8)

        self.side_title = QLabel("素材分组")
        lay.addWidget(self.side_title)

        self.group_box = QVBoxLayout()
        self.group_box.setSpacing(1)
        lay.addLayout(self.group_box)

        self.btn_import = QPushButton("＋ 导入素材")
        self.btn_import.setObjectName("primary")
        self.btn_import.setCursor(Qt.PointingHandCursor)
        self.btn_import.clicked.connect(self.on_import)
        lay.addWidget(self.btn_import)

        self.import_hint = QLabel("支持视频与图片\n原始文件不会被移动或修改")
        self.import_hint.setWordWrap(True)
        lay.addWidget(self.import_hint)

        lay.addStretch(1)
        return self.side

    # ---------- 中：素材区 ----------
    def _build_main(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(14, 12, 14, 10)
        lay.setSpacing(8)

        # 项目行
        top = QHBoxLayout()
        top.setSpacing(8)
        self.proj_label = QLabel("未打开项目")
        top.addWidget(self.proj_label)
        top.addStretch(1)
        self.btn_new = QPushButton("新建项目")
        self.btn_open = QPushButton("打开项目")
        for b in (self.btn_new, self.btn_open):
            b.setCursor(Qt.PointingHandCursor)
            top.addWidget(b)
        self.btn_new.clicked.connect(self.on_new_project)
        self.btn_open.clicked.connect(self.on_open_project)
        lay.addLayout(top)

        # 进度
        prow = QHBoxLayout()
        prow.setSpacing(10)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        self.progress_label = QLabel("—")
        prow.addWidget(self.progress, 1)
        prow.addWidget(self.progress_label)
        lay.addLayout(prow)

        # 统计条
        self.stats_row = QHBoxLayout()
        self.stats_row.setSpacing(6)
        lay.addLayout(self.stats_row)

        # 警告条（异常素材）
        self.warn_bar = QLabel("")
        self.warn_bar.setWordWrap(True)
        self.warn_bar.setVisible(False)
        lay.addWidget(self.warn_bar)

        # 网格
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(10)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.scroll.setWidget(self.grid_host)
        lay.addWidget(self.scroll, 1)

        # 底部操作
        foot = QHBoxLayout()
        foot.setSpacing(8)
        self.btn_analyze = QPushButton("开始分析")
        self.btn_analyze.setObjectName("primary")
        self.btn_analyze.setCursor(Qt.PointingHandCursor)
        self.btn_analyze.clicked.connect(self.on_analyze)

        self.btn_confirm = QPushButton("查看待确认")
        self.btn_confirm.setCursor(Qt.PointingHandCursor)
        self.btn_confirm.clicked.connect(self.on_show_confirm)

        self.btn_remove = QPushButton("移除选中")
        self.btn_remove.setCursor(Qt.PointingHandCursor)
        self.btn_remove.setObjectName("danger")
        # 【阶段B修复 20261121 增补】先选中卡片按钮才会亮，提示避免误以为功能坏了
        self.btn_remove.setToolTip("先单击选中素材卡片，再点这里移除")
        self.btn_remove.clicked.connect(self.on_remove_selected)
        self.btn_remove.setEnabled(False)

        self.btn_next = QPushButton("下一步：剪辑方案 →")
        self.btn_next.setCursor(Qt.PointingHandCursor)
        self.btn_next.clicked.connect(self.request_open_storyboard.emit)

        foot.addWidget(self.btn_analyze)
        foot.addWidget(self.btn_confirm)
        foot.addWidget(self.btn_remove)
        foot.addStretch(1)
        foot.addWidget(self.btn_next)
        lay.addLayout(foot)
        return w

    # ---------- 右：商品信息与参数 ----------
    def _build_info(self):
        self.info = QFrame()
        self.info.setFixedWidth(308)
        lay = QVBoxLayout(self.info)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

        self.info_title = QLabel("商品信息")
        lay.addWidget(self.info_title)

        self.lab_name = QLabel("商品名称")
        self.ed_name = QLineEdit()
        self.ed_name.setPlaceholderText("例如：带灯床头柜")
        lay.addWidget(self.lab_name)
        lay.addWidget(self.ed_name)

        self.lab_sell = QLabel("功能卖点")
        self.ed_sell = QTextEdit()
        self.ed_sell.setPlaceholderText("例如：抽屉顺滑、三色温可切换、灯头可调节\n（不确定的功能请留空，系统不会编造）")
        self.ed_sell.setFixedHeight(76)
        lay.addWidget(self.lab_sell)
        lay.addWidget(self.ed_sell)

        self.btn_save_info = QPushButton("保存商品信息")
        self.btn_save_info.setCursor(Qt.PointingHandCursor)
        self.btn_save_info.clicked.connect(self.on_save_product)
        lay.addWidget(self.btn_save_info)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        self._sep1 = line
        lay.addWidget(line)

        self.param_title = QLabel("制作参数")
        lay.addWidget(self.param_title)

        # 比例
        rrow = QHBoxLayout()
        self.lab_ratio = QLabel("画面比例")
        self.cb_ratio = QComboBox()
        for k in ("3:4 竖版", "9:16 竖屏", "1:1 正方形", "16:9 横屏"):
            self.cb_ratio.addItem(k)
        rrow.addWidget(self.lab_ratio)
        rrow.addWidget(self.cb_ratio, 1)
        lay.addLayout(rrow)

        # 时长
        drow = QHBoxLayout()
        self.lab_dur = QLabel("目标时长")
        self.sp_dur = QSpinBox()
        self.sp_dur.setRange(10, 90)
        self.sp_dur.setValue(30)
        self.sp_dur.setSuffix(" 秒")
        drow.addWidget(self.lab_dur)
        drow.addWidget(self.sp_dur, 1)
        lay.addLayout(drow)

        # 字幕
        srow = QHBoxLayout()
        self.lab_sub = QLabel("字幕样式")
        self.cb_sub = QComboBox()
        self.cb_sub.addItem("卖点标签（推荐）", "selling_badge")
        self.cb_sub.addItem("标准整句", "standard")
        srow.addWidget(self.lab_sub)
        srow.addWidget(self.cb_sub, 1)
        lay.addLayout(srow)

        # 开关
        self.ck_voice = QCheckBox("配音（默认关闭）")
        self.ck_voice.setChecked(False)
        self.ck_bgm = QCheckBox("背景音乐")
        self.ck_bgm.setChecked(True)
        self.ck_sub = QCheckBox("字幕")
        self.ck_sub.setChecked(True)
        lay.addWidget(self.ck_voice)
        lay.addWidget(self.ck_bgm)
        lay.addWidget(self.ck_sub)

        self.btn_save_param = QPushButton("保存制作参数")
        self.btn_save_param.setCursor(Qt.PointingHandCursor)
        self.btn_save_param.clicked.connect(self.on_save_params)
        lay.addWidget(self.btn_save_param)

        lay.addStretch(1)

        # 能力说明（诚实告知）
        self.cap_box = QLabel("")
        self.cap_box.setWordWrap(True)
        lay.addWidget(self.cap_box)
        return self.info

    # ================= 主题 =================
    def set_dark(self, dark):
        self._dark = dark
        self.apply_theme()

    def apply_theme(self):
        t = dt.tokens(self._dark)
        self.side.setStyleSheet(f"QFrame{{background-color:{t['surface']};"
                               f"border-right:1px solid {t['border']};}}")
        self.info.setStyleSheet(f"QFrame{{background-color:{t['surface']};"
                               f"border-left:1px solid {t['border']};}}")
        self.side_title.setStyleSheet(
            f"font-size:{dt.FS_HINT}px;font-weight:700;color:{t['hint']};")
        self.import_hint.setStyleSheet(f"font-size:{dt.FS_HINT}px;color:{t['hint']};")
        self.proj_label.setStyleSheet(
            f"font-size:{dt.FS_TITLE}px;font-weight:600;color:{t['text']};")
        self.progress_label.setStyleSheet(f"font-size:{dt.FS_HINT}px;color:{t['muted']};")
        self.warn_bar.setStyleSheet(
            f"QLabel{{background-color:{t['warning_bg']};color:{t['warning']};"
            f"border:1px solid {t['warning']};border-radius:{dt.R_MD}px;"
            f"padding:6px 10px;font-size:{dt.FS_HINT}px;}}")
        for lab in (self.info_title, self.param_title):
            lab.setStyleSheet(f"font-size:{dt.FS_BIG}px;font-weight:600;color:{t['text']};")
        for lab in (self.lab_name, self.lab_sell, self.lab_ratio, self.lab_dur,
                    self.lab_sub):
            lab.setStyleSheet(f"font-size:{dt.FS_HINT}px;color:{t['muted']};")
        self._sep1.setStyleSheet(f"QFrame{{color:{t['border']};max-height:1px;}}")
        self.cap_box.setStyleSheet(
            f"QLabel{{background-color:{t['warning_bg']};color:{t['warning']};"
            f"border:1px solid {t['warning']};border-radius:{dt.R_MD}px;"
            f"padding:8px 10px;font-size:{dt.FS_HINT}px;}}")
        for c in (self.ck_voice, self.ck_bgm, self.ck_sub):
            c.setStyleSheet(f"QCheckBox{{font-size:{dt.FS_BODY}px;color:{t['text']};}}")
        # 刷新卡片与统计
        for card in self._cards.values():
            card.apply_theme(self._dark)
        self._refresh_groups()
        self._refresh_stats()

    # ================= 数据绑定 =================
    def bind_project(self, db, project):
        self.db = db
        self.project = project
        # 【阶段B修复 20261121 增补】同步项目路径，供导入/删除后刷新使用
        self.db_path = str(getattr(db, "db_path", "") or "")
        self._group = "全部"
        self._selected.clear()
        self.proj_label.setText(project.name)
        self._load_product()
        self._load_params()
        self.refresh_all()

    def refresh_all(self):
        self._refresh_groups()
        self._refresh_stats()
        self._refresh_grid()
        self._refresh_capability()

    def _refresh_capability(self):
        if not self.db:
            self.cap_box.setText("尚未打开项目。")
            return
        cap = bridge.ai_capability_summary(self.db)
        self.cap_box.setText(
            "能力说明\n"
            f"· 分析来源：{M.ANALYZER_LABEL.get(cap['analyzer_in_use'], '未知')}\n"
            "· 未接入视觉/语言模型，无法识别商品动作语义\n"
            "· 识别引擎未通过正式集成验收")

    def _refresh_groups(self):
        # 清空
        while self.group_box.count():
            item = self.group_box.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        if not self.project:
            return
        for g in self.project.groups:
            row = GroupRow(g.name, g.count, g.name == self._group, self._dark)
            row.clicked.connect(lambda r=row: self._on_group(r.group_name))
            self.group_box.addWidget(row)
        self.group_box.addStretch(1)

    def _on_group(self, name):
        self._group = name
        self._refresh_groups()
        self._refresh_grid()

    def _refresh_stats(self):
        while self.stats_row.count():
            item = self.stats_row.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        if not self.project:
            self.progress.setValue(0)
            self.progress_label.setText("—")
            return
        s = self.project.stats
        chips = [
            StatChip(s.total, "条素材", "muted", False, self._dark),
            StatChip(s.analyzed, "已分析", "success" if s.analyzed else "muted", False, self._dark),
            StatChip(s.confirm, "待确认", "warning" if s.confirm else "muted",
                     s.confirm > 0, self._dark),
            StatChip(s.unanalyzed, "未分析", "muted", False, self._dark),
        ]
        if s.failed:
            chips.append(StatChip(s.failed, "读取失败", "danger", False, self._dark))
        if s.images:
            chips.append(StatChip(s.images, "张图片", "muted", False, self._dark))
        for c in chips:
            self.stats_row.addWidget(c)
            if c is chips[2] and s.confirm > 0:
                c.clicked.connect(self.on_show_confirm)
        self.stats_row.addStretch(1)

        self.progress.setValue(s.progress_pct)
        self.progress_label.setText(f"已分析 {s.analyzed} / {s.total}")

        bad = [a for a in self.project.assets if a.status == M.ST_FAILED]
        if bad:
            names = "、".join(a.filename for a in bad[:3])
            more = f" 等 {len(bad)} 条" if len(bad) > 3 else ""
            self.warn_bar.setText(f"⚠ 有素材读取失败，无法参与剪辑：{names}{more}")
            self.warn_bar.setVisible(True)
        else:
            self.warn_bar.setVisible(False)

        self.btn_confirm.setText(f"查看待确认（{s.confirm}）")
        self.btn_confirm.setEnabled(s.confirm > 0)
        self.btn_analyze.setEnabled(s.unanalyzed > 0)

    def _refresh_grid(self):
        # 清空网格
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self._cards.clear()
        self._selected.clear()
        self.btn_remove.setEnabled(False)

        if not self.project:
            es = EmptyState("还没有打开项目",
                            "先新建一个项目，或打开已有项目，然后导入素材。",
                            "新建项目", self._dark)
            es.action.connect(self.on_new_project)
            self.grid.addWidget(es, 0, 0)
            return

        assets = self.project.assets
        if self._group != "全部":
            assets = [a for a in assets if a.group == self._group]

        if not assets:
            es = EmptyState(
                "这个分组还没有素材" if self.project.assets else "还没有素材",
                "把视频或图片拖进来，或点左下角「导入素材」。\n"
                "支持 mp4/mov 等视频，以及 jpg/png 等图片。",
                "导入素材", self._dark)
            es.action.connect(self.on_import)
            self.grid.addWidget(es, 0, 0)
            return

        cols = max(1, (self.scroll.viewport().width() - 8) // (AssetCard.CARD_W + 10))
        for i, a in enumerate(assets):
            card = AssetCard(a, self._dark)
            card.clicked.connect(lambda vm=a: self._on_card_click(vm, Qt.LeftButton))
            card.double_clicked.connect(lambda vm=a: self._on_card_double(vm))
            self.grid.addWidget(card, i // cols, i % cols)
            self._cards[a.asset_id] = card

    def _on_card_click(self, vm, button):
        # 简单选中态：切换高亮
        if vm.asset_id in self._selected:
            self._selected.discard(vm.asset_id)
        else:
            self._selected.add(vm.asset_id)
        card = self._cards.get(vm.asset_id)
        if card:
            t = dt.tokens(self._dark)
            card.setStyleSheet(dt.inline("card_on" if vm.asset_id in self._selected else "card",
                                         self._dark))
        self.btn_remove.setEnabled(bool(self._selected))

    def _on_card_double(self, vm):
        AssetDetailDialog(vm, self._dark, self).exec()

    # ================= 操作：项目 =================
    def on_new_project(self):
        from ...db import ProjectDB
        name, ok = _ask_text(self, "新建项目", "项目名称", "新的商品视频")
        if not ok or not name.strip():
            return
        from ... import config
        safe = "".join(c for c in name.strip() if c not in r'\/:*?"<>|')[:40] or "project"
        path = config.DB_DIR / f"{safe}.db"
        n = 1
        while path.exists():
            path = config.DB_DIR / f"{safe}_{n}.db"
            n += 1
        try:
            db = ProjectDB(path)
            db.set_project_name(name.strip())
            db.init_storyboards([s for s in config.DEFAULT_STORYBOARD_TEMPLATE])
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "新建失败", f"{type(e).__name__}: {e}")
            return
        self.status_message.emit(f"已新建项目：{name}")
        self._open_db(db, path)

    def on_open_project(self):
        from ... import config
        path, _ = QFileDialog.getOpenFileName(
            self, "打开项目", str(config.DB_DIR), "项目数据库 (*.db)")
        if not path:
            return
        from ...db import ProjectDB
        try:
            db = ProjectDB(path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "打开失败", f"{type(e).__name__}: {e}")
            return
        self._open_db(db, path)

    def _open_db(self, db, path):
        project = bridge.load_project(db, path)
        self.db = db
        self.project = project
        # 【阶段B修复 20261121 增补】同步项目路径，供导入/删除后刷新使用
        self.db_path = str(path)
        self.proj_label.setText(project.name)
        self._load_product()
        self._load_params()
        self.refresh_all()
        self.status_message.emit(
            f"已打开：{project.name} · {len(project.assets)} 条素材")

    # ================= 操作：导入 =================
    def on_import(self):
        if not self.db:
            QMessageBox.information(self, "还没有项目", "请先新建或打开一个项目。")
            return
        exts = " ".join("*" + e for e in sorted(_all_exts()))
        paths, _ = QFileDialog.getOpenFileNames(
            self, "导入素材（视频或图片）", "",
            f"素材文件 ({exts});;所有文件 (*.*)")
        if not paths:
            return
        self._import_paths(paths)

    def _import_paths(self, paths):
        if not self.db:
            return
        ok = fail = skip = img_ok = 0
        errors = []
        for p in paths:
            if not img.is_supported(p):
                skip += 1
                errors.append(f"{Path(p).name}：不支持的格式")
                continue
            try:
                info = img.probe_any(p)
                if info.get("error") or not info.get("decode_ok"):
                    fail += 1
                    errors.append(f"{Path(p).name}：{info.get('error', '无法读取')}")
                    continue
                info["thumb_path"] = img.make_thumb_any(p, info.get("duration_ms", 0))
                self.db.add_asset(info)
                ok += 1
                if info.get("kind") == "image":
                    img_ok += 1
            except Exception as e:  # noqa: BLE001 - 单条失败不拖垮整批
                fail += 1
                errors.append(f"{Path(p).name}：{type(e).__name__}: {e}")

        # 重新读项目
        self.project = bridge.load_project(self.db, self.db_path or getattr(self.db, "db_path", ""))
        self.refresh_all()

        msg = f"导入完成：成功 {ok}"
        if img_ok:
            msg += f"（其中图片 {img_ok}）"
        if fail:
            msg += f"，失败 {fail}"
        if skip:
            msg += f"，跳过 {skip}"
        self.status_message.emit(msg)

        if errors:
            QMessageBox.warning(self, "部分素材未能导入",
                                "\n".join(errors[:10]) +
                                ("\n…" if len(errors) > 10 else ""))

    # ================= 操作：移除 =================
    def on_remove_selected(self):
        if not self.db or not self._selected:
            return
        n = len(self._selected)
        ans = QMessageBox.question(
            self, "确认移除",
            f"从项目中移除选中的 {n} 条素材？\n\n"
            "只从项目记录里移除，不会删除磁盘上的原始文件。")
        if ans != QMessageBox.Yes:
            return
        removed = 0
        for aid in list(self._selected):
            try:
                self.db.delete_asset(aid)
                removed += 1
            except Exception:  # noqa: BLE001
                pass
        self.project = bridge.load_project(self.db, self.db_path or "")
        self._selected.clear()
        self.refresh_all()
        self.status_message.emit(f"已移除 {removed} 条素材（原始文件未动）")

    # ================= 操作：分析 =================
    def on_analyze(self):
        if not self.db or not self.project:
            return
        # 只分析"未分析"的视频；图片当前不做自动分析（渲染链尚不支持静帧）
        targets = [a for a in self.project.assets
                   if a.status == M.ST_UNANALYZED and not a.is_image and a.decode_ok]
        imgs_pending = [a for a in self.project.assets
                        if a.status == M.ST_UNANALYZED and a.is_image]
        if not targets:
            if imgs_pending:
                QMessageBox.information(
                    self, "图片暂不自动分析",
                    f"有 {len(imgs_pending)} 张图片尚未分析。\n\n"
                    "当前版本图片只支持导入与展示；静帧进入成片需要在导出环节支持，"
                    "属阶段 D 范围。")
            else:
                QMessageBox.information(self, "没有需要分析的素材",
                                        "所有视频都已分析过了。")
            return

        items = [(a.asset_id, a.path, a.duration_ms) for a in targets]
        self.btn_analyze.setEnabled(False)
        self.btn_analyze.setText(f"分析中 0/{len(items)}…")
        self.progress.setRange(0, 0)  # 不确定进度

        task_id = self.db.add_task("镜头分析", input_file=f"{len(items)} 个素材")
        w = AnalyzeWorker(items, do_dedup=False, parent=self)
        self._analyze_worker = w

        def on_prog(cur, total, name):
            self.btn_analyze.setText(f"分析中 {cur}/{total}…")
            self.status_message.emit(f"正在分析 {cur}/{total}：{name}")

        def on_file(asset_id, payload):
            result, kf_map = payload
            if result is None:
                err = (kf_map or {}).get("error", "未知错误")
                self.status_message.emit(f"素材分析失败：{err}")
                return
            try:
                self.db.save_scene_analysis(asset_id, result, kf_map)
            except Exception as e:  # noqa: BLE001
                self.status_message.emit(f"保存分析结果失败：{e}")

        def on_done(ok, fail):
            self.progress.setRange(0, 100)
            self.btn_analyze.setText("开始分析")
            try:
                self.db.finish_task(task_id, "成功" if fail == 0 else "部分失败",
                                    f"成功 {ok}，失败 {fail}")
            except Exception:  # noqa: BLE001
                pass
            self.project = bridge.load_project(self.db, self.db_path or "")
            self.refresh_all()
            self.status_message.emit(f"分析完成：成功 {ok}，失败 {fail}")
            self._analyze_worker = None
            if fail:
                QMessageBox.warning(
                    self, "部分素材分析失败",
                    f"成功 {ok} 条，失败 {fail} 条。\n"
                    "失败的素材已标记，可重新导入或检查文件是否损坏。")

        w.progress.connect(on_prog)
        w.file_done.connect(on_file)
        w.all_done.connect(on_done)
        w.start()

    # ================= 操作：待确认 =================
    def on_show_confirm(self):
        if not self.db:
            return
        pend = [c for c in (self.db.get_clips() or [])
                if (c.get("verify_state") or "") == "待核验"]
        if not pend:
            QMessageBox.information(self, "没有待确认项", "当前所有分析结果都不需要人工确认。")
            return
        ConfirmDialog(pend, self.db, self._dark, self).exec()
        self.project = bridge.load_project(self.db, self.db_path or "")
        self.refresh_all()

    # ================= 操作：商品信息 / 参数 =================
    def _load_product(self):
        if not self.db:
            return
        info = self.db.get_product_info() or {}
        self.ed_name.setText(str(info.get("name") or ""))
        self.ed_sell.setPlainText(str(info.get("selling") or ""))

    def on_save_product(self):
        if not self.db:
            return
        from ...core import narration as nar
        name = self.ed_name.text().strip()
        sell = self.ed_sell.toPlainText().strip()
        # 违禁词校验（复用既有护栏，用户自己填的也要校验）
        bad = []
        for w in nar.FORBIDDEN_CLAIMS:
            if w in sell:
                bad.append(w)
        if bad:
            QMessageBox.warning(
                self, "卖点里有未核实的说法",
                "以下词需要资质或检测报告才能写，建议删掉：\n"
                + "、".join(bad))
            return
        info = dict(self.db.get_product_info() or {})
        info["name"] = name
        info["selling"] = sell
        self.db.set_product_info(info)
        self.status_message.emit("商品信息已保存")

    def _load_params(self):
        if not self.db:
            return
        st = self.db.get_settings() or {}
        ratio = st.get("workshop_ratio", "3:4 竖版")
        idx = self.cb_ratio.findText(ratio)
        if idx >= 0:
            self.cb_ratio.setCurrentIndex(idx)
        try:
            self.sp_dur.setValue(int(st.get("workshop_target_s", "30")))
        except ValueError:
            self.sp_dur.setValue(30)
        style = st.get("workshop_sub_style", "selling_badge")
        si = self.cb_sub.findData(style)
        if si >= 0:
            self.cb_sub.setCurrentIndex(si)
        self.ck_voice.setChecked(st.get("workshop_voice", "0") == "1")
        self.ck_bgm.setChecked(st.get("workshop_bgm", "1") == "1")
        self.ck_sub.setChecked(st.get("workshop_sub", "1") == "1")

    def on_save_params(self):
        if not self.db:
            return
        self.db.set_setting("workshop_ratio", self.cb_ratio.currentText())
        self.db.set_setting("workshop_target_s", str(self.sp_dur.value()))
        self.db.set_setting("workshop_sub_style", self.cb_sub.currentData())
        self.db.set_setting("workshop_voice", "1" if self.ck_voice.isChecked() else "0")
        self.db.set_setting("workshop_bgm", "1" if self.ck_bgm.isChecked() else "0")
        self.db.set_setting("workshop_sub", "1" if self.ck_sub.isChecked() else "0")
        self.status_message.emit("制作参数已保存")


# ============================================================================
# 辅助对话框
# ============================================================================
def _all_exts():
    from ... import config
    return set(config.VIDEO_EXTS) | set(img.IMAGE_EXTS)


def _ask_text(parent, title, label, default=""):
    from PySide6.QtWidgets import QInputDialog
    return QInputDialog.getText(parent, title, label, text=default)


class AssetDetailDialog(QDialog):
    """点素材看详情：缩略图 + 元数据 + 分析来源（诚实说明）。"""

    def __init__(self, vm, dark=False, parent=None):
        super().__init__(parent)
        self._dark = dark
        self.setWindowTitle(f"素材详情 · {vm.filename}")
        self.resize(460, 480)
        t = dt.tokens(dark)
        self.setStyleSheet(dt.qss(dark))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 12)
        lay.setSpacing(10)

        from .widgets import Thumb
        thumb = Thumb(180, 220, dark)
        if vm.thumb_path:
            thumb.load(vm.thumb_path)
        else:
            thumb.show_placeholder("无缩略图")
        lay.addWidget(thumb, 0, Qt.AlignHCenter)

        rows = [
            ("文件名", vm.filename),
            ("类型", vm.kind_text),
            ("状态", vm.status_label),
            ("时长", vm.duration_text),
            ("分辨率", vm.size_text),
            ("分组", vm.group),
            ("镜头数", str(vm.shot_count)),
            ("待确认", str(vm.pending_count)),
            ("分析来源", vm.analyzer_label),
        ]
        for k, v in rows:
            row = QHBoxLayout()
            kl = QLabel(k)
            kl.setFixedWidth(70)
            kl.setStyleSheet(f"font-size:{dt.FS_HINT}px;color:{t['hint']};")
            vl = QLabel(v)
            vl.setWordWrap(True)
            vl.setStyleSheet(f"font-size:{dt.FS_BODY}px;color:{t['text']};")
            row.addWidget(kl)
            row.addWidget(vl, 1)
            lay.addLayout(row)

        if vm.note:
            note = QLabel(vm.note)
            note.setWordWrap(True)
            note.setStyleSheet(
                f"QLabel{{background-color:{t['warning_bg']};color:{t['warning']};"
                f"border:1px solid {t['warning']};border-radius:{dt.R_MD}px;"
                f"padding:8px;font-size:{dt.FS_HINT}px;}}")
            lay.addWidget(note)

        path_lab = QLabel(vm.path)
        path_lab.setWordWrap(True)
        path_lab.setStyleSheet(f"font-size:{dt.FS_HINT - 1}px;color:{t['hint']};")
        lay.addWidget(path_lab)

        lay.addStretch(1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok)
        bb.button(QDialogButtonBox.Ok).setText("知道了")
        bb.accepted.connect(self.accept)
        lay.addWidget(bb)


class ConfirmDialog(QDialog):
    """待人工确认列表。

    阶段 B 只做**只读展示 + 标记为已核验**，不做功能语义确认
    （功能标签 L2 属阶段 C/E，届时才写入 analysis_candidates）。
    """

    def __init__(self, pend, db, dark=False, parent=None):
        super().__init__(parent)
        self._pend = pend
        self._db = db
        self._dark = dark
        self.setWindowTitle(f"待人工确认（{len(pend)} 条）")
        self.resize(680, 560)
        t = dt.tokens(dark)
        self.setStyleSheet(dt.qss(dark))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 12)
        lay.setSpacing(8)

        tip = QLabel(
            "这些是算法测量给出、但还拿不准的候选片段。\n"
            "当前系统只能测「画面在变」，说不出「这是抽屉打开」——"
            "所以需要你看着画面判断。")
        tip.setWordWrap(True)
        tip.setStyleSheet(
            f"QLabel{{background-color:{t['info_bg']};color:{t['primary']};"
            f"border:1px solid {t['info_border']};border-radius:{dt.R_MD}px;"
            f"padding:8px 10px;font-size:{dt.FS_HINT}px;}}")
        lay.addWidget(tip)

        self.list = QListWidget()
        assets = {a["id"]: a for a in (db.get_assets() or [])}
        for c in pend:
            a = assets.get(c.get("asset_id"), {})
            name = a.get("filename", "?")
            t0 = (c.get("start_ms") or 0) / 1000
            t1 = (c.get("end_ms") or 0) / 1000
            tag = c.get("primary_tag") or "未命名"
            reason = (c.get("cut_reason") or c.get("potential_issue") or "").strip()
            item = QListWidgetItem(
                f"{name}  {t0:.1f}–{t1:.1f}s  [{tag}]\n"
                f"    依据：{reason or '（无说明）'}")
            item.setData(Qt.UserRole, c.get("id"))
            item.setToolTip("双击可标记为已核验（不改变画面内容）")
            self.list.addItem(item)
        lay.addWidget(self.list, 1)

        brow = QHBoxLayout()
        self.btn_ok = QPushButton("标记选中为已核验")
        self.btn_ok.setCursor(Qt.PointingHandCursor)
        self.btn_ok.clicked.connect(self._mark_ok)
        self.btn_all = QPushButton("全部标记为已核验")
        self.btn_all.setCursor(Qt.PointingHandCursor)
        self.btn_all.clicked.connect(self._mark_all)
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.accept)
        brow.addWidget(self.btn_ok)
        brow.addWidget(self.btn_all)
        brow.addStretch(1)
        brow.addWidget(btn_close)
        lay.addLayout(brow)

    def _mark(self, items):
        n = 0
        for it in items:
            cid = it.data(Qt.UserRole)
            try:
                self._db.update_clip(cid, verify_state="已确认")
                n += 1
            except Exception:  # noqa: BLE001
                pass
        QMessageBox.information(self, "已更新", f"已把 {n} 条标记为已核验。")
        self.accept()

    def _mark_ok(self):
        sel = self.list.selectedItems()
        if not sel:
            QMessageBox.information(self, "请先选中", "请在列表里选中要标记的条目。")
            return
        self._mark(sel)

    def _mark_all(self):
        self._mark([self.list.item(i) for i in range(self.list.count())])
