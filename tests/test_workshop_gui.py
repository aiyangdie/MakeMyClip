# -*- coding: utf-8 -*-
"""阶段 B · 三页工作台 GUI 冒烟测试（offscreen，无窗口弹出）

覆盖：
  1. 窗口能创建，三页容器就位
  2. 打开真实项目 → 素材卡真实渲染
  3. 主题切换（亮↔暗）不崩
  4. 分组筛选生效
  5. 空项目空态
  6. 阶段 B 未实现的页面明确提示、不假装能用
  7. 顶栏 AI 标识如实（不得宣称 AI 理解）
  8. 截图留证（亮/暗/空态/1366x768）

运行：从项目根目录 `.venv/Scripts/python.exe tests/test_workshop_gui.py`
"""
import json
import os
import sys
import tempfile
import shutil
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402

checks = []
SHOTS = []


def ck(name, cond, detail=""):
    checks.append({"name": name, "ok": bool(cond), "detail": str(detail)})


class MessageBoxSpy:
    """拦截模态弹窗，避免 offscreen 下阻塞，同时记录弹了什么。"""

    def __init__(self):
        self.calls = []
        self._orig = {}

    def __enter__(self):
        for n in ("information", "warning", "critical", "question"):
            self._orig[n] = getattr(QMessageBox, n)
            setattr(QMessageBox, n, self._mk(n))
        return self

    def _mk(self, kind):
        def _f(parent, title, text, *a, **kw):
            self.calls.append({"kind": kind, "title": title, "text": text})
            return QMessageBox.Yes
        return _f

    def __exit__(self, *exc):
        for n, f in self._orig.items():
            setattr(QMessageBox, n, f)
        return False

    def last(self):
        return self.calls[-1] if self.calls else {}


def shot(win, name):
    p = ROOT / "tests" / f"gui_workshop_{name}.png"
    win.grab().save(str(p))
    SHOTS.append(str(p.name))
    return p.exists()


def main():
    app = QApplication.instance() or QApplication([])
    from app.ui.workshop import WorkspaceWindow

    # ---------- 1. 创建 ----------
    win = WorkspaceWindow()
    win.show()
    app.processEvents()
    ck("窗口能创建", win is not None)
    ck("三页容器就位", win.stack.count() == 3, win.stack.count())
    ck("启动时停在页面一", win.stack.currentIndex() == 0, win.stack.currentIndex())
    ck("窗口标题含'工作台'", "工作台" in win.windowTitle(), win.windowTitle())

    # ---------- 2. AI 标识必须如实 ----------
    ai_text = win.topbar.ai_badge.text()
    ck("顶栏 AI 标识写明'非 AI 理解'", "非 AI 理解" in ai_text, ai_text)
    ck("顶栏 AI 标识含'基础算法'", "基础算法" in ai_text, ai_text)

    # ---------- 3. 空项目空态 ----------
    tmp = Path(tempfile.mkdtemp(prefix="mmc_wsgui_"))
    empty_db = tmp / "empty.db"
    win.open_project(str(empty_db))
    app.processEvents()
    pg = win.page_workspace
    ck("空项目：素材卡数为 0", len(pg._cards) == 0, len(pg._cards))
    ck("空项目：显示空态而不是空白", pg.grid.count() >= 1, pg.grid.count())
    ck("空项目：开始分析按钮禁用", not pg.btn_analyze.isEnabled())
    ck("空项目截图", shot(win, "01_empty"))

    # ---------- 4. 打开真实项目 ----------
    demo = ROOT / "projects" / "_stage9_full.db"
    ck("真实演示库存在", demo.exists(), str(demo))
    if demo.exists():
        ok = win.open_project(str(demo))
        app.processEvents()
        ck("打开真实项目成功", ok is True)
        ck("项目名已显示", bool(win.page_workspace.proj_label.text())
           and win.page_workspace.proj_label.text() != "未打开项目",
           win.page_workspace.proj_label.text())
        n_assets = len(win.project.assets)
        ck("素材数 > 0", n_assets > 0, n_assets)
        ck("素材卡真实渲染（数量与素材数一致）", len(pg._cards) == n_assets,
           f"cards={len(pg._cards)} assets={n_assets}")
        ck("分组列表有内容", pg.group_box.count() >= 2, pg.group_box.count())
        ck("统计条有内容", pg.stats_row.count() >= 4, pg.stats_row.count())
        ck("亮色截图", shot(win, "02_light"))

        # 分组筛选
        groups = [g.name for g in win.project.groups if g.name != "全部"]
        if groups:
            g0 = groups[0]
            expect = len([a for a in win.project.assets if a.group == g0])
            pg._on_group(g0)
            app.processEvents()
            ck(f"筛选分组'{g0}'后卡片数正确", len(pg._cards) == expect,
               f"cards={len(pg._cards)} expect={expect}")
            pg._on_group("全部")
            app.processEvents()
            ck("切回'全部'恢复全部卡片", len(pg._cards) == n_assets, len(pg._cards))

        # 主题切换
        win._toggle_theme()
        app.processEvents()
        ck("切到暗色", win._dark is True)
        ck("暗色下卡片仍存在", len(pg._cards) == n_assets, len(pg._cards))
        ck("暗色截图", shot(win, "03_dark"))
        win._toggle_theme()
        app.processEvents()
        ck("切回亮色", win._dark is False)

        # 卡片选中
        first_id = list(pg._cards.keys())[0]
        vm = next(a for a in win.project.assets if a.asset_id == first_id)
        pg._on_card_click(vm, Qt.LeftButton)
        app.processEvents()
        ck("点卡片能选中", first_id in pg._selected, pg._selected)
        ck("选中后'移除'按钮可用", pg.btn_remove.isEnabled())
        pg._on_card_click(vm, Qt.LeftButton)
        app.processEvents()
        ck("再点一次取消选中", first_id not in pg._selected)
        ck("取消后'移除'按钮禁用", not pg.btn_remove.isEnabled())

        # 待确认计数（不真的弹 QDialog，避免 offscreen 下阻塞）
        pend = [c for c in (win.db.get_clips() or [])
                if (c.get("verify_state") or "") == "待核验"]
        ck("待确认计数与库一致",
           pg.btn_confirm.text() == f"查看待确认（{len(pend)}）",
           f"{pg.btn_confirm.text()} vs {len(pend)}")
        ck("有待确认项时按钮可点 / 无则禁用",
           pg.btn_confirm.isEnabled() == (len(pend) > 0),
           f"enabled={pg.btn_confirm.isEnabled()} pend={len(pend)}")

    # ---------- 5. 阶段 B 未实现页面必须明确提示 ----------
    with MessageBoxSpy() as spy:
        win._goto_page(1)
        app.processEvents()
    ck("点'剪辑方案'会明确告知未实现（不假装能用）",
       bool(spy.calls) and "未实现" in spy.last().get("title", ""),
       spy.last().get("title", ""))
    ck("告知后仍停在页面一", win.stack.currentIndex() == 0, win.stack.currentIndex())

    with MessageBoxSpy() as spy2:
        win._goto_page(2)
        app.processEvents()
    ck("点'预览与导出'会明确告知未实现",
       bool(spy2.calls) and "未实现" in spy2.last().get("title", ""))
    ck("占位页文字说明了计划内容",
       "阶段 C" in win.page_storyboard.n.text() or "阶段 D" in win.page_preview.n.text(),
       win.page_storyboard.n.text())

    # ---------- 6. 1366x768 适配 ----------
    win.resize(1366, 768)
    app.processEvents()
    ck("1366x768 下窗口尺寸正确",
       win.width() == 1366 and win.height() == 768, f"{win.width()}x{win.height()}")
    ck("1366x768 截图", shot(win, "04_1366x768"))
    # 三栏总宽不应超出窗口
    pg2 = win.page_workspace
    total_w = pg2.side.width() + pg2.info.width()
    ck("左右侧栏宽度之和小于窗口宽度", total_w < 1366, total_w)

    # ---------- 7. 页面内部不写死颜色（复用设计令牌） ----------
    sheet = win.styleSheet()
    ck("窗口套用了统一 QSS（非空）", len(sheet) > 500, len(sheet))
    ck("QSS 里没有残留的旧阶段色值 #2F6BEF 硬编码在界面文件里",
       "#2F6BEF" not in Path(ROOT / "app/ui/workshop/page_workspace.py")
       .read_text(encoding="utf-8").lower())

    shutil.rmtree(tmp, ignore_errors=True)

    # ---------- 汇总 ----------
    passed = sum(1 for c in checks if c["ok"])
    out = {
        "stage": "B",
        "suite": "workshop_gui",
        "total": len(checks),
        "passed": passed,
        "failed": len(checks) - passed,
        "checks": checks,
        "screenshots": SHOTS,
    }
    (ROOT / "tests" / "test_result_workshop_gui.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"WORKSHOP_GUI {passed}/{len(checks)}")
    for c in checks:
        if not c["ok"]:
            print(f"  FAIL {c['name']}  {c['detail']}")
    print("截图:", ", ".join(SHOTS))
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
