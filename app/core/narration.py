# -*- coding: utf-8 -*-
"""商品文案生成（阶段五）。

铁律（对应任务书 4.8 / 8.3）：
- 只使用用户在『商品资料』里亲手填写的真实信息。
- 未填写的字段一律不写进文案，并明确列入 missing 提醒用户补全。
- 绝不凭空生成尺寸、材质、承重、功率、色温数值、认证或未证实效果。
- 文案与镜头一一对应（按 timeline 镜头），用户可逐句编辑覆盖。

这里的“生成”是模板化拼装用户已确认的事实，不是大模型自由创作——
这样可以 100% 保证不编造商品参数。以后若要接大语言模型，可替换 build_all 内部，
但必须同样经过 missing 校验，且模型输出不得引入未填写字段。
"""
import json

# 每个分镜的默认旁白模板：只用 {name} 镜头语义 + 用户填的真实字段占位。
# 模板句不含任何具体参数；参数只在用户填写后才由 _filled_facts 注入。
SHOT_TEMPLATES = {
    "产品整体亮相": "接下来为您展示{product}的整体外观。",
    "整体亮相": "接下来为您展示{product}的整体外观。",
    "台面材质和边缘": "台面细节与边缘处理，尽收眼底。",
    "台面材质细节": "来看台面的细节。",
    "拉手特写": "拉手的设计细节，一同看一下。",
    "抽屉开合": "抽屉的开合过程，平稳顺畅。",
    "抽屉内部": "抽屉内部空间，一览无余。",
    "柜脚和底部": "柜脚与底部结构，稳固扎实。",
    "灯杆调节": "灯杆可以进行调节。",
    "灯头旋转": "灯头支持角度调整。",
    "三色温切换": "灯光可以切换不同的照明效果。",
    "灯罩细节": "灯罩的外观细节。",
    "实体开关按钮": "实体开关，操作方便。",
    "整体收尾": "以上就是{product}的整体展示。",
    "商品整体收尾": "以上就是{product}的整体展示。",
}
FALLBACK_TEMPLATE = "现在为您展示：{shot_name}。"

# 用户可能填写的商品字段（只在有值时进入文案）
FACT_FIELDS = ["name", "color", "material", "size", "scene", "selling", "function"]
FACT_LABEL = {
    "name": "商品名称", "color": "颜色", "material": "材质", "size": "尺寸",
    "scene": "使用场景", "selling": "卖点", "function": "功能",
}
# 明确禁止模型/模板臆造的高风险字段：即便字段存在也要用户确认来源
SENSITIVE_FIELDS = ["load_bearing", "power", "color_temp_value", "certification"]
SENSITIVE_LABEL = {
    "load_bearing": "承重参数", "power": "灯光功率",
    "color_temp_value": "色温具体数值", "certification": "产品认证",
}


def load_product_info(settings):
    """从项目 settings 读取商品资料 settings['product_info'] (JSON str)。"""
    raw = settings.get("product_info", "") if settings else ""
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        return {}


def validate_product_info(info):
    """返回 (missing, sensitive_warnings)：未填字段 + 高风险字段提醒。"""
    missing = [FACT_LABEL[k] for k in ("name", "color", "material") if not (info.get(k) or "").strip()]
    warnings = [SENSITIVE_LABEL.get(k, k) + "（需确认来源真实，未确认则不写入文案）"
                for k in SENSITIVE_FIELDS if (info.get(k) or "").strip()]
    return missing, warnings


def build_all(shots, product_info):
    """按时间线镜头生成逐句文案。

    shots: [{'shot_id','name',...}, ...]（timeline 行）
    返回 {'lines': [...], 'title': str, 'missing': [...], 'warnings': [...]}
    line = {'shot_id','name','text','start_ms','end_ms','source':'template'}
    """
    info = product_info or {}
    missing, warnings = validate_product_info(info)
    product = (info.get("name") or "").strip() or "这款商品"

    lines = []
    # 字幕时间必须按镜头在成片中的实际顺序累计，而不是素材内起止时间。
    # 缺素材镜头不进成片，因此不生成字幕行——否则字幕会堆在 0 秒处闪烁。
    timeline_ms = 0
    for sh in shots:
        name = (sh.get("name") or "").strip()
        if not (sh.get("asset_path") or "").strip():
            continue  # 缺素材镜头跳过，不进成片也就不该有字幕
        tmpl = SHOT_TEMPLATES.get(name, FALLBACK_TEMPLATE)
        text = tmpl.format(product=product, shot_name=name)
        # 【阶段七】成片中该镜头的实际时长必须与渲染结果对齐，字幕才不漂移：
        #   1) 联动镜头 = 各子片段(建议时长或起止差)之和 - 每处衔接的短叠化
        #   2) 普通镜头优先用建议时长 target_ms（渲染按它定格补足/截短）
        #   3) 兜底：duration_ms / 起止差 / 3 秒
        dur = 0
        subs_raw = sh.get("sub_segments") or ""
        subs = []
        if isinstance(subs_raw, list):
            subs = subs_raw
        elif isinstance(subs_raw, str) and subs_raw.strip():
            try:
                v = json.loads(subs_raw)
                subs = v if isinstance(v, list) else []
            except Exception:
                subs = []
        if subs:
            from .. import config as _config
            tr_ms = int(getattr(_config, "DEFAULT_SUB_TRANSITION_S", 0.4) * 1000)
            total = 0
            for sb in subs:
                sd = sb.get("target_ms") or 0
                if not sd:
                    sd = max(0, (sb.get("end_ms", 0) or 0) - (sb.get("start_ms", 0) or 0))
                total += sd
            dur = max(0, total - max(0, len(subs) - 1) * tr_ms)
        elif sh.get("target_ms"):
            dur = sh["target_ms"]
        else:
            dur = sh.get("duration_ms") or 0
            if not dur:
                dur = max(0, (sh.get("end_ms", 0) or 0) - (sh.get("start_ms", 0) or 0))
        if dur <= 0:
            dur = 3000  # 兜底默认 3 秒，避免 0 长度字幕
        line = {
            "shot_id": sh.get("shot_id", ""),
            "name": name,
            "text": text,
            "start_ms": timeline_ms,
            "end_ms": timeline_ms + dur,
            "source": "template",
        }
        lines.append(line)
        timeline_ms += dur

    title = (f"{product} 商品展示" if info.get("name") else "商品展示（未填写商品名称）")
    return {
        "lines": lines, "title": title,
        "missing": missing, "warnings": warnings,
        "used_product_name": bool(info.get("name")),
    }


def fill_line_from_product(text, info):
    """供外部调用：在已确认 info 下做安全的占位替换（不引入新事实）。"""
    product = (info.get("name") or "").strip() or "这款商品"
    return text.replace("{product}", product)


# ===========================================================================
# 【阶段十增补 · 参考片风格「卖点标签」文案】
# 参考真实淘宝主图视频：字幕是 4-8 字卖点短语，配合一镜一卖点快切。
# 铁律：这些标签只描述「镜头里真实拍到的画面动作/部件」，不含任何
#       材质、工艺、承重、功率、认证、环保等未经核实的宣称。
#       参考片里的「软包皮质/优质五金/碳素钢/全实木/环保无异味」是它自家
#       商品的说法，咱们一个字都不搬。全部标签均可被用户逐句编辑覆盖。
# 原 build_all / SHOT_TEMPLATES 保留不动（标准模式行为不变）。
# ===========================================================================

# 镜头名 -> (卖点标签, 版式 kind)。只写画面可证内容。
SELLING_LABELS = {
    "产品整体亮相": ("带灯床头柜", "title"),
    "台面材质和边缘": ("台面细节", "tag"),
    "触摸柜面质感": ("手抚柜面", "tag"),
    "拉手特写": ("圆形拉手", "tag"),
    "抽屉开合": ("抽屉开合", "tag"),
    "抽屉内部": ("抽屉内部", "tag"),
    "柜脚和底部": ("柜脚细节", "tag"),
    "灯杆调节": ("灯杆高度可调", "tag"),
    "灯杆伸缩调节": ("灯杆高度可调", "tag"),
    "灯头旋转": ("灯头可旋转", "tag"),
    "灯罩细节": ("灯罩细节", "tag"),
    "实体开关按钮": ("实体开关", "tag"),
    "三色温切换": ("三色灯光", "big"),
    "按钮触发三色灯": ("三色灯光", "big"),
    "整体收尾": ("带灯床头柜", "title"),
    "商品整体收尾": ("带灯床头柜", "title"),
}
DEFAULT_SELLING_LABEL = ("细节展示", "tag")

# 明确禁止出现在卖点标签里的一切未核实宣称（护栏，测试会校验）
FORBIDDEN_CLAIMS = [
    "皮质", "软包", "真皮", "五金", "碳素钢", "不锈钢", "实木", "板材",
    "环保", "无异味", "无甲醛", "承重", "防水", "阻燃", "认证",
    "功率", "瓦", "色温值", "进口", "专利", "质保", "十年",
]


def build_selling_lines(shots, product_info=None):
    """按时间线镜头生成「卖点标签」式逐句文案（参考片风格）。

    与 build_all 相同：字幕时间按成片中镜头实际顺序累计，缺素材镜头跳过；
    联动镜头按子片段建议时长合计减叠化；保证字幕与画面严格对位。
    每条 line 额外带 'kind'（tag/title/big）供字幕排版选用版式。
    """
    info = product_info or {}
    product = (info.get("name") or "").strip() or "带灯床头柜"
    missing, warnings = validate_product_info(info)

    # 第一遍：算出每个镜头在成片里的"片段时长" d_i 和标签内容
    stage = []
    for sh in shots:
        name = (sh.get("name") or "").strip()
        _subs_chk = sh.get("sub_segments")
        _has_subs = bool(_subs_chk) if isinstance(_subs_chk, list) else bool((_subs_chk or "").strip())
        if not (sh.get("asset_path") or "").strip() and not _has_subs:
            continue  # 缺素材镜头不进成片
        label, kind = SELLING_LABELS.get(name, DEFAULT_SELLING_LABEL)
        if kind == "title" and (info.get("name") or "").strip():
            label = product
        dur = 0
        subs_raw = sh.get("sub_segments") or ""
        subs = []
        if isinstance(subs_raw, list):
            subs = subs_raw
        elif isinstance(subs_raw, str) and subs_raw.strip():
            try:
                v = json.loads(subs_raw)
                subs = v if isinstance(v, list) else []
            except Exception:
                subs = []
        if subs:
            from .. import config as _config
            tr_ms = int(getattr(_config, "DEFAULT_SUB_TRANSITION_S", 0.4) * 1000)
            total = 0
            for sb in subs:
                sd = sb.get("target_ms") or 0
                if not sd:
                    sd = max(0, (sb.get("end_ms", 0) or 0) - (sb.get("start_ms", 0) or 0))
                total += sd
            dur = max(0, total - max(0, len(subs) - 1) * tr_ms)
        elif sh.get("target_ms"):
            dur = sh["target_ms"]
        else:
            dur = sh.get("duration_ms") or 0
            if not dur:
                dur = max(0, (sh.get("end_ms", 0) or 0) - (sh.get("start_ms", 0) or 0))
        if dur <= 0:
            dur = 3000
        stage.append({"shot_id": sh.get("shot_id", ""), "name": name,
                      "text": label, "kind": kind, "dur": dur})

    # 第二遍：按成片真实时间轴精确对齐。
    # 渲染层用 xfade 叠化：相邻片段重叠 transition_s，故第 i 段在成片中的
    # 起点 = 前面各段时长之和 - (i-1)*t。字幕按 [offset_i, offset_{i+1}) 覆盖，
    # 首尾严丝合缝、不漂移（旧逻辑直接累加 d_i 会越往后越滞后）。
    from .. import config as _config
    t_ms = int(getattr(_config, "DEFAULT_TRANSITION_S", 0.4) * 1000)
    n = len(stage)
    lines = []
    cum = 0
    for i, st in enumerate(stage):
        start = cum - i * t_ms
        cum += st["dur"]
        # 字幕覆盖到"下一段开始淡入"为止；最后一段延伸到成片末尾
        end = cum - (i + 1) * t_ms if i + 1 < n else cum - (n - 1) * t_ms
        lines.append({
            "shot_id": st["shot_id"], "name": st["name"],
            "text": st["text"], "kind": st["kind"],
            "start_ms": max(0, start), "end_ms": max(start + 200, end),
            "source": "selling_label",
        })

    return {
        "lines": lines, "title": f"{product} 商品展示",
        "missing": missing, "warnings": warnings,
        "used_product_name": bool(info.get("name")),
        "timeline_ms": cum - max(0, n - 1) * t_ms,
    }


def validate_selling_labels(lines):
    """护栏：确认所有标签都不含未核实宣称。返回违规列表（应永远为空）。"""
    bad = []
    for ln in lines:
        t = ln.get("text", "")
        for w in FORBIDDEN_CLAIMS:
            if w in t:
                bad.append(f"{ln.get('name','?')}: 含禁用词「{w}」")
    return bad


def kind_for_name(name):
    """按镜头名返回卖点标签版式 kind（tag/title/big）。"""
    return SELLING_LABELS.get((name or "").strip(), DEFAULT_SELLING_LABEL)[1]


def decorate_lines(lines):
    """给普通逐句文案补上 kind 字段（供卖点标签排版使用），不改文字/时间。"""
    out = []
    for ln in lines:
        d = dict(ln)
        d.setdefault("kind", kind_for_name(ln.get("name", "")))
        out.append(d)
    return out


def calibrate_to_duration(lines, actual_ms):
    """把字幕时间线整体线性校准到成片真实时长（最后一道保险）。

    渲染层每处叠化的实际重叠量可能有几十毫秒舍入，累积起来会让末尾
    字幕飘出画面。这里按真实时长等比缩放所有起止点，保证首尾严格贴合。
    不改任何文字。返回新的 lines（原列表不动）。
    """
    lines = list(lines or [])
    if not lines or not actual_ms or actual_ms <= 0:
        return lines
    last = max((ln.get("end_ms", 0) or 0) for ln in lines)
    if last <= 0:
        return lines
    ratio = float(actual_ms) / float(last)
    if abs(ratio - 1.0) < 0.001:
        return lines
    out = []
    for ln in lines:
        d = dict(ln)
        d["start_ms"] = int(round((ln.get("start_ms", 0) or 0) * ratio))
        d["end_ms"] = int(round((ln.get("end_ms", 0) or 0) * ratio))
        out.append(d)
    return out
