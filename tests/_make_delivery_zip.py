# -*- coding: utf-8 -*-
"""把项目成果打成一份干净、能看懂的交付包（不含可再生的大体积依赖/缓存）。

只读取现有文件，不改动任何源文件。运行：
    .venv/Scripts/python.exe tests/_make_delivery_zip.py
输出：项目根目录 / MakeMyClip_交付包_YYYYMMDD.zip
"""
import datetime
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STAMP = datetime.date.today().strftime("%Y%m%d")
OUT = ROOT / f"MakeMyClip_成果交付包_{STAMP}.zip"

# 打包映射：(包内路径, 磁盘真实路径)。目录会自动递归，但跳过 SKIP_DIR 里的东西。
SKIP_DIR = {"__pycache__", ".venv", "cache", ".git", ".pytest_cache"}
SKIP_EXT = {".pyc", ".pyo"}

ITEMS = []


def add_dir(prefix, rel):
    """把一个目录整体收进包的 prefix 下。"""
    base = ROOT / rel
    if not base.is_dir():
        return
    for p in sorted(base.rglob("*")):
        if not p.is_file():
            continue
        if any(part in SKIP_DIR for part in p.relative_to(ROOT).parts):
            continue
        if p.suffix.lower() in SKIP_EXT:
            continue
        ITEMS.append((f"{prefix}/{p.relative_to(base).as_posix()}", p))


def add_file(arc, rel):
    p = ROOT / rel
    if p.is_file():
        ITEMS.append((arc, p))


# ---- 01 程序源代码 ----
add_dir("01_程序源代码/app", "app")
for f in ("main.py", "main_wizard.py", "mcp_server.py",
          "requirements.txt", "一键启动.bat", "安装依赖.bat"):
    add_file(f"01_程序源代码/{f}", f)

# ---- 02 说明与全部阶段报告 ----
for f in ("使用说明.md", "技术调查报告.md", "素材清单与初步候选核对表.md"):
    add_file(f"02_说明与报告/{f}", f)
for p in sorted(ROOT.glob("阶段*报告.md")):
    add_file(f"02_说明与报告/{p.name}", p.name)

# ---- 03 界面截图（真实离屏渲染，中文字体正常）----
for p in sorted((ROOT / "tests").glob("*.png")):
    add_file(f"03_界面截图/{p.name}", f"tests/{p.name}")

# ---- 04 测试脚本与验收结果 ----
for p in sorted((ROOT / "tests").iterdir()):
    if p.is_file() and p.suffix.lower() in (".py", ".json"):
        if p.name.startswith("_make_delivery_zip"):
            continue
        add_file(f"04_测试与验收/{p.name}", f"tests/{p.name}")

# ---- 05 可回退备份（改前整包）----
add_dir("05_备份_可回退", "backups")

# ---- 06 项目库 ----
for p in sorted((ROOT / "projects").glob("*.db")):
    add_file(f"06_项目库/{p.name}", f"projects/{p.name}")

# ---- 07 成片样例（只挑 2 条代表性的，其余 32 条仍在 exports/）----
for name in ("一键出片_参考片风格_20261121_033220.mp4", "阶段十_参考片风格.mp4"):
    add_file(f"07_成片样例/{name}", f"exports/{name}")

# ---- 08 模板与日志 ----
add_file("08_模板与日志/furniture_nightstand.json", "templates/furniture/nightstand.json")
add_file("08_模板与日志/agent_ops.log", "logs/agent_ops.log")

# ---- 桌面启动器 ----
DESK = Path("C:/Users/Administrator/Desktop/MakeMyClip.cmd")
if DESK.is_file():
    ITEMS.append(("桌面启动器_MakeMyClip.cmd", DESK))

# ---- 包内清单：说人话，先讲「这对你意味着什么」----
MANIFEST = f"""# 先看这个 · 成果交付包清单（{STAMP}）

## 这个包是什么

这是《AI 家具电商视频自动剪辑系统》从阶段一到阶段十三做出来的**全部成果文件**：
程序、13 份阶段报告、使用说明、界面截图、测试记录、改前备份、项目库、成片样例、桌面启动器。

一句话：**给你留档、核对、以及万一要回退用的**。

## 包里有什么（按文件夹）

| 文件夹 | 里面是什么 | 对你有什么用 |
|---|---|---|
| 01_程序源代码 | 全部 Python 程序、3 个入口、依赖清单、两个 .bat | 软件的「里子」，找人维护时用 |
| 02_说明与报告 | 使用说明 + 技术调查报告 + 素材核对表 + 阶段一~十三共 13 份报告 | 想知道「每一步做了什么、怎么测的」看这里 |
| 03_界面截图 | 22 张真实界面图，含阶段十一/十二/十三、浅色/深色 | 不用开软件就能看到界面长什么样 |
| 04_测试与验收 | 各阶段测试脚本 + 测试结果 json（阶段十三 81/81） | 验收证据 |
| 05_备份_可回退 | pre_stage11 / 12 / 13 三批改前整包备份 + 哈希基线 | 不满意哪一版，把对应文件拷回去即可 |
| 06_项目库 | 11 个 .db 项目文件（含演示库） | 项目数据 |
| 07_成片样例 | 2 条代表性成片（3:4 竖版 720×960，约 30 秒） | 直接看剪辑效果 |
| 08_模板与日志 | 分镜模板、智能体操作审计日志 | 追溯用 |
| 桌面启动器_MakeMyClip.cmd | 你桌面上那个启动器的副本 | 换电脑时参考 |

## 这个包里**没有**什么（都在电脑上，没丢）

- **.venv 依赖环境（581M）**：软件运行要用的第三方库，电脑上已经装好了，换电脑时双击「安装依赖.bat」能重装。它体积太大、又不是「成果」，所以没塞进来。
- **cache 渲染缓存（293M）**：剪片时的中间文件，删了会自动重新生成，不算成果。
- **其余 32 条历史成片（约 120M）**：全部完整保存在项目的 `exports/` 文件夹里，一条都没删；这里只挑 2 条代表性的，免得包太大。
- **35 条原始素材视频**：是**你提供的、只读**的，从不改动、也从不打包外发。

## 要运行软件，别用这个包

这个包是**留档用的分类整理**，目录结构跟实际运行目录不一样，直接解压来跑会找不到路径。

要在电脑上用软件：**双击桌面原来的「MakeMyClip」启动器**就行，或进原来的
`MakeMyClip` 文件夹双击「一键启动.bat」。程序和依赖一直都在那儿，没动过。

## 最近这次（阶段十三）改了什么

界面按 Material 3 / shadcn / Figma 社区的公开设计规矩整体重做：一步一屏、说人话、
圆点进度可跳步、右上角浅色/深色一键切换、专业设置收起。**出片/字幕/渲染/导出/
原素材/旧成片/桌面启动器/旧工作台一个字节都没动**。验收 81/81，真实出片一条。

详情看 `02_说明与报告/阶段十三报告.md` 和 `02_说明与报告/使用说明.md` 末尾的【v13.0 增补】。
"""

with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    z.writestr("00_先看这个_文件清单.md", MANIFEST)
    for arc, disk in ITEMS:
        z.write(disk, arc)

size = OUT.stat().st_size
print(f"ZIP = {OUT}")
print(f"FILES = {len(ITEMS) + 1}  (含清单)")
print(f"SIZE = {size / 1024 / 1024:.1f} MB")
print("---- 分类统计 ----")
from collections import Counter
c = Counter(a.split("/")[0] for a, _ in ITEMS)
for k in sorted(c):
    print(f"  {k}: {c[k]}")
