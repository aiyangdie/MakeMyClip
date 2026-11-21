# -*- coding: utf-8 -*-
"""后台任务：用 QThread 执行耗时操作，避免阻塞界面。"""
from PySide6.QtCore import QThread, Signal

from . import media
from .core import scene_detector, duplicate_detector, quality_scorer
from .ai import vision_provider, tts_provider


class ImportWorker(QThread):
    """批量导入视频：逐个探测元数据 + 抽缩略图，实时回报进度。"""
    progress = Signal(int, int, str)   # 当前, 总数, 文件名
    one_done = Signal(dict)            # 单条结果（含元数据）
    all_done = Signal(int, int)        # 成功数, 失败数

    def __init__(self, file_paths, parent=None):
        super().__init__(parent)
        self.file_paths = list(file_paths)
        self._abort = False

    def stop(self):
        self._abort = True

    def run(self):
        ok = fail = 0
        total = len(self.file_paths)
        for i, path in enumerate(self.file_paths, 1):
            if self._abort:
                break
            self.progress.emit(i, total, path.rsplit("\\", 1)[-1].rsplit("/", 1)[-1])
            info = media.probe(path)
            if not info.get("error") and info.get("decode_ok"):
                info["thumb_path"] = media.make_thumb(path, info.get("duration_ms", 0))
                ok += 1
            else:
                fail += 1
            self.one_done.emit(info)
        self.all_done.emit(ok, fail)


class AnalyzeWorker(QThread):
    """批量镜头分析：对每条素材做镜头切分 + 关键帧，最后做重复检测。

    全程可取消；单条失败只记录错误，不中断整批。
    """
    progress = Signal(int, int, str)       # 当前, 总数, 文件名
    file_done = Signal(int, object)        # asset_id, scene_result
    dedup_done = Signal(object)            # duplicate groups
    all_done = Signal(int, int)            # 成功, 失败

    def __init__(self, items, do_dedup=True, parent=None):
        """items: [(asset_id, path, duration_ms), ...]"""
        super().__init__(parent)
        self.items = list(items)
        self.do_dedup = do_dedup
        self._abort = False

    def stop(self):
        self._abort = True

    def run(self):
        ok = fail = 0
        total = len(self.items)
        analyzed = []
        for i, (asset_id, path, duration_ms) in enumerate(self.items, 1):
            if self._abort:
                break
            name = path.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
            self.progress.emit(i, total, name)
            try:
                result = scene_detector.analyze_video(path)
                if not result.get("ok"):
                    fail += 1
                    continue
                # 为每个镜头抽关键帧
                kf_map = {}
                for shot in result["shots"]:
                    frames = media.extract_keyframes(
                        path, shot["end_ms"] - shot["start_ms"],
                        interval_sec=1.0, max_frames=5)
                    # 关键帧时间要加上镜头起点偏移
                    for f in frames:
                        f["time_ms"] += shot["start_ms"]
                    kf_map[shot["index"]] = [f["path"] for f in frames]
                self.file_done.emit(asset_id, (result, kf_map))
                analyzed.append({"id": asset_id, "path": path, "result": result})
                ok += 1
            except Exception as e:  # noqa: BLE001 - 单文件失败不拖垮批处理
                self.file_done.emit(asset_id, (None, {"error": f"{type(e).__name__}: {e}"}))
                fail += 1

        if self.do_dedup and not self._abort and analyzed:
            try:
                assets = [{"path": a["path"], "filename": a["path"].rsplit("\\", 1)[-1]}
                          for a in analyzed]
                groups = duplicate_detector.detect(assets)
                self.dedup_done.emit(groups)
            except Exception:  # noqa: BLE001
                self.dedup_done.emit({"exact_groups": [], "similar_groups": [], "details": {}})

        self.all_done.emit(ok, fail)


class SemanticWorker(QThread):
    """对候选片段逐条做视觉识别 + 质量评分（阶段三）。

    items: [(clip_id, asset_path, start_ms, end_ms), ...]
    全程可取消；单片段失败只记录错误，不中断整批。
    """
    progress = Signal(int, int, str)        # 当前, 总数, 文件名
    one_done = Signal(int, dict, dict)      # clip_id, vision, quality
    all_done = Signal(int, int)             # 成功, 失败

    def __init__(self, items, provider_name=None, parent=None):
        super().__init__(parent)
        self.items = list(items)
        self.provider = vision_provider.provider_factory(provider_name)
        self._abort = False

    def stop(self):
        self._abort = True

    def run(self):
        ok = fail = 0
        total = len(self.items)
        for i, (clip_id, path, start_ms, end_ms) in enumerate(self.items, 1):
            if self._abort:
                break
            name = path.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
            self.progress.emit(i, total, name)
            try:
                vision = self.provider.analyze_segment(path, start_ms, end_ms)
                quality = quality_scorer.score_segment(path, start_ms, end_ms)
                if not vision.get("ok") or not quality.get("ok"):
                    fail += 1
                else:
                    ok += 1
                self.one_done.emit(clip_id, vision, quality)
            except Exception as e:  # noqa: BLE001
                fail += 1
                self.one_done.emit(clip_id,
                                   {"ok": False, "error": f"{type(e).__name__}: {e}",
                                    "labels": [], "metrics": {}},
                                   {"ok": False, "error": str(e), "total": 0})
        self.all_done.emit(ok, fail)


class RenderWorker(QThread):
    """按时间线生成成片：逐镜头渲染(带缓存) -> 拼接 -> 校验（阶段四）。

    全程可取消；单镜头失败记录原因，不中断其余镜头。
    """
    progress = Signal(int, int, str, bool)   # 当前, 总数, shot_id, 是否缓存命中
    done = Signal(dict)                      # 渲染结果 + 成片信息

    def __init__(self, shots, export_params, output_path, db=None, parent=None):
        super().__init__(parent)
        from .core import video_editor
        self.video_editor = video_editor
        self.shots = list(shots)
        self.export_params = dict(export_params)
        self.output_path = output_path
        self.db = db
        self._abort = False

    def stop(self):
        self._abort = True

    def run(self):
        def on_prog(done_n, total, sid, cached):
            self.progress.emit(done_n, total, sid, cached)

        def cancelled():
            return self._abort

        r = self.video_editor.render_all(
            self.shots, self.export_params, db=self.db,
            progress_cb=on_prog, cancel_cb=cancelled)
        result = dict(r)
        if self._abort:
            result["ok"] = False
            result["errors"].append({"shot_id": "", "error": "用户取消"})
            self.done.emit(result)
            return
        if r["ok"]:
            transition = self.export_params.get("transition", "none")
            transition_s = self.export_params.get("transition_s", 0.4)
            out = self.video_editor.concat_segments(
                r["segments"], self.output_path,
                transition=transition, transition_s=transition_s)
            result["output"] = out
            if out["ok"]:
                result["verify"] = self.video_editor.probe_output(out["path"])
        self.done.emit(result)


class TTSWorker(QThread):
    """逐句生成中文配音（阶段五）。可取消；单句失败不中断其余。"""
    progress = Signal(int, int, str)          # 当前, 总数, 文案摘要
    one_done = Signal(str, dict, str)         # line_id, 合成结果, 文案
    all_done = Signal(int, int)               # 成功, 失败

    def __init__(self, items, voice_id=None, rate=160, volume=1.0, parent=None):
        """items: [(line_id, text), ...]"""
        super().__init__(parent)
        self.items = list(items)
        self.voice_id = voice_id
        self.rate = rate
        self.volume = volume
        self._abort = False

    def stop(self):
        self._abort = True

    def run(self):
        ok = fail = 0
        total = len(self.items)
        provider = tts_provider.provider_factory()
        for i, (line_id, text) in enumerate(self.items, 1):
            if self._abort:
                break
            self.progress.emit(i, total, (text or "")[:16])
            try:
                r = tts_provider.synthesize_cached(
                    text, voice_id=self.voice_id, rate=self.rate,
                    volume=self.volume, provider=provider)
                if r.get("ok"):
                    ok += 1
                else:
                    fail += 1
                self.one_done.emit(line_id, r, text)
            except Exception as e:  # noqa: BLE001
                fail += 1
                self.one_done.emit(line_id,
                                   {"ok": False, "error": f"{type(e).__name__}: {e}"}, text)
        self.all_done.emit(ok, fail)


class FinalExportWorker(QThread):
    """最终合成：无声成片 + 字幕 + 旁白 + 音乐 -> 最终MP4（阶段五）。"""
    progress = Signal(int, int, str)
    done = Signal(dict)

    def __init__(self, silent_video, lines, subtitle_path, out_path, options, parent=None):
        super().__init__(parent)
        self.silent_video = silent_video
        self.lines = lines
        self.subtitle_path = subtitle_path
        self.out_path = out_path
        self.options = dict(options)
        self._abort = False

    def stop(self):
        self._abort = True

    def run(self):
        from .core import final_exporter

        def on_prog(cur, tot, msg):
            self.progress.emit(cur, tot, msg)

        r = final_exporter.export_final(
            self.silent_video, self.lines, self.subtitle_path, self.out_path,
            progress_cb=on_prog, **self.options)
        if self._abort:
            r["ok"] = False
            r["error"] = "用户取消"
        self.done.emit(r)
