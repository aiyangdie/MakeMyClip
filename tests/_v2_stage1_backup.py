# -*- coding: utf-8 -*-
"""V2.0 第一阶段：改前完整备份 + SHA256 基线。

只读复制，不改动任何现有文件；不复制 .venv / cache / 历史成片等可再生物。
运行：.venv/Scripts/python.exe tests/_v2_stage1_backup.py
产出：backups/pre_v2/  +  BASELINE_SHA256.txt  +  BACKUP_MANIFEST.md
"""
import hashlib
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BK = ROOT / "backups" / "pre_v2"
BK.mkdir(parents=True, exist_ok=True)

# 明确排除：可再生 / 体积大 / 非成果
SKIP_DIR = {"__pycache__", ".venv", "cache", ".git", ".pytest_cache", "exports"}
SKIP_EXT = {".pyc", ".pyo", ".zip"}

# 需要备份的目录与顶层文件
DIRS = ["app", "templates", "tests", "projects", "logs"]
TOP_FILES = [
    "main.py", "main_wizard.py", "mcp_server.py",
    "requirements.txt", "一键启动.bat", "安装依赖.bat",
    "使用说明.md", "技术调查报告.md", "素材清单与初步候选核对表.md",
    "交付包文件清单.md",
]
TOP_FILES += [p.name for p in sorted(ROOT.glob("阶段*报告.md"))]
DESK = Path("C:/Users/Administrator/Desktop/MakeMyClip.cmd")

records = []  # (备份内相对名, 源真实路径, sha256, 字节数)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def collect(src: Path, arcname: str):
    if src.is_dir():
        for p in sorted(src.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(src)
            if any(part in SKIP_DIR for part in rel.parts):
                continue
            if p.suffix.lower() in SKIP_EXT:
                continue
            records.append((f"{arcname}/{rel.as_posix()}", p, sha(p), p.stat().st_size))
    elif src.is_file():
        records.append((arcname, src, sha(src), src.stat().st_size))


for d in DIRS:
    collect(ROOT / d, d)
for f in TOP_FILES:
    p = ROOT / f
    if p.is_file():
        collect(p, f)
if DESK.is_file():
    collect(DESK, "Desktop_MakeMyClip.cmd")

# 复制
for arc, src, _, _ in records:
    dst = BK / arc
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    if sha(dst) != sha(src):
        raise RuntimeError(f"备份校验失败: {arc}")

# 基线
lines = ["# V2.0 改前基线 SHA256（第一阶段）",
         f"# 生成时间: {datetime.now().isoformat(timespec='seconds')}",
         f"# 文件数: {len(records)}", "# 格式: SHA256  bytes  arcname", ""]
for arc, _, h, n in sorted(records):
    lines.append(f"{h}  {n}  {arc}")
(BK / "BASELINE_SHA256.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

# 清单
from collections import Counter
c = Counter(a.split("/")[0] for a, _, _, _ in records)
ml = ["# V2.0 第一阶段 · 改前备份清单", "",
      f"- 备份位置：`backups/pre_v2/`",
      f"- 文件总数：**{len(records)}**",
      f"- 总字节：{sum(r[3] for r in records):,}",
      f"- 基线文件：`BASELINE_SHA256.txt`（逐个 SHA256）", "",
      "## 分类", "", "| 分类 | 文件数 |", "|---|---|"]
for k in sorted(c):
    ml.append(f"| {k} | {c[k]} |")
ml += ["", "## 刻意未备份（可再生 / 非代码 / 体积过大）", "",
       "- `.venv/`：依赖环境 581M，双击「安装依赖.bat」可重装",
       "- `cache/`：渲染缓存 293M，会自动重建",
       "- `exports/`：历史成片 131M（34 条），**原件全部保留未动**，仅不重复备份",
       "- `__pycache__/`、`.pyc`、旧 `.zip` 交付包",
       "- 35 条原始素材：在桌面 `T26单抽视频/`，**只读、从不复制、从不改动**", "",
       "## 回退方法", "",
       "把 `backups/pre_v2/` 内对应文件按相对名覆盖回项目根即可；",
       "用 `BASELINE_SHA256.txt` 逐个核对哈希确认一致。"]
(BK / "BACKUP_MANIFEST.md").write_text("\n".join(ml) + "\n", encoding="utf-8")

print(f"BACKUP_DIR = {BK}")
print(f"FILES = {len(records)}")
print(f"BYTES = {sum(r[3] for r in records):,}")
for k in sorted(c):
    print(f"  {k}: {c[k]}")
print("BASELINE_OK =", (BK / "BASELINE_SHA256.txt").is_file())
