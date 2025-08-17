from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from enum import Enum
from io import TextIOWrapper
from fastapi.responses import FileResponse
import csv
import uuid
from typing import Optional
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import uuid

router = APIRouter()

# ─────────────────────────────────────────────────────────────
# アクション定義
# ─────────────────────────────────────────────────────────────
class Action(str, Enum):
    sum = "sum"                        # 1) インプレッション合計
    pie_gender = "pie_gender"          # 2) 性別別インプレッション割合
    ctr_top3 = "ctr_top3"              # 3) CTR上位3
    fix_encoding = "fix_encoding"      # 4) 文字コード修正（UTF-8 BOMへ）
    split_1000 = "split_1000"          # 5) 1000行分割
    merge = "merge"                    # 6) 2CSV結合（ヘッダー一致）

# 列名候補（lowerで比較）
IMP_KEYS = {"impressions", "impression", "imp", "表示回数", "表示"}
CLK_KEYS = {"clicks", "click", "クリック数", "クリック"}
GENDER_KEYS = {"gender", "性別"}
CREATIVE_KEYS = {"creative", "クリエイティブ", "ad", "ad_name", "adname", "素材名", "広告名", "creative name"}

# ─────────────────────────────────────────────────────────────
# ヘルパー
# ─────────────────────────────────────────────────────────────
def _open_text(file: UploadFile) -> TextIOWrapper:
    """
    CSVをテキストで開く。utf-8-sig → utf-8 → cp932 の順に試す。
    """
    raw = file.file.read()
    file.file.seek(0)
    for enc in ("utf-8-sig", "utf-8", "cp932"):
        try:
            raw.decode(enc)
            file.file.seek(0)
            return TextIOWrapper(file.file, encoding=enc, newline="")
        except Exception:
            continue
    raise HTTPException(status_code=400, detail="Unsupported file encoding")

def _normalize_header(fieldnames: list[str] | None) -> dict[str, str]:
    """ {lower_name: original_name} """
    return {name.strip().lower(): name for name in (fieldnames or [])}

def _find_col_exact(field_map: dict[str, str], candidates: set[str]) -> Optional[str]:
    for lower, original in field_map.items():
        if lower in candidates:
            return original
    return None

def _find_col_fuzzy(field_map: dict[str, str], candidates: set[str], substrings: list[str]) -> Optional[str]:
    """正確一致→部分一致の順で列名を探す（返すのは元の列名）"""
    hit = _find_col_exact(field_map, candidates)
    if hit:
        return hit
    for lower, original in field_map.items():
        if any(sub in lower for sub in substrings):
            return original
    return None

def _safe_int(x) -> int:
    s = str(x).replace(",", "").strip()
    if not s:
        return 0
    try:
        return int(float(s))
    except ValueError:
        return 0

def _unique(name: str) -> str:
    """出力ファイル名を一意化"""
    base, dot, ext = name.partition(".")
    return f"{base}_{uuid.uuid4().hex[:8]}{dot}{ext}" if dot else f"{name}_{uuid.uuid4().hex[:8]}"

# ─────────────────────────────────────────────────────────────
# メインエンドポイント（/process にマウントされる前提）
# ─────────────────────────────────────────────────────────────
@router.post("")
async def process(
    action: Action = Form(...),
    file: UploadFile | None = File(None),
    file2: UploadFile | None = File(None),
):
    # 1) impressions 合計
    if action == Action.sum:
        if not file:
            raise HTTPException(status_code=400, detail="file is required for sum")
        try:

            wrapper = _open_text(file)
            reader = csv.DictReader(wrapper)
            fmap = _normalize_header(reader.fieldnames)
            imp_key = _find_col_fuzzy(fmap, IMP_KEYS, ["imp", "impression", "表示"])
            if not imp_key:
                raise HTTPException(status_code=400, detail={"error": "Column 'impressions' not found", "headers_seen": list(fmap.values())})
            total = 0
            for row in reader:
                total += _safe_int(row.get(imp_key, ""))
            return {"action": "sum", "impressions_total": total}
        finally:
            try: file.file.close()
            except Exception: pass

    # 2) 性別別インプレッション割合（円グラフPNGを返す）
    if action == Action.pie_gender:
        if not file:
            raise HTTPException(status_code=400, detail="file is required for pie_gender")
        try:
            wrapper = _open_text(file)
            reader = csv.DictReader(wrapper)
            fmap = _normalize_header(reader.fieldnames)
            imp_key = _find_col_fuzzy(fmap, IMP_KEYS, ["imp", "impression", "表示"])
            gen_key = _find_col_fuzzy(fmap, GENDER_KEYS, ["gender", "性別"])
            if not (imp_key and gen_key):
                raise HTTPException(
                    status_code=400,
                    detail={"error": "Columns 'gender' or 'impressions' not found",
                            "headers_seen": list(fmap.values())}
                )

            totals: dict[str, int] = {}
            grand = 0
            for row in reader:
                g = (row.get(gen_key, "") or "").strip() or "不明"
                v = _safe_int(row.get(imp_key, ""))
                totals[g] = totals.get(g, 0) + v
                grand += v

            if grand == 0:
                # データがないときはJSONで知らせる
                return {"action": "pie_gender", "percentages": {}, "total_impressions": 0}

            # ラベル・値
            labels = list(totals.keys())
            values = [totals[k] for k in labels]
            percentages = [round(v / grand * 100, 1) for v in values]

            # 円グラフ作成
            fig, ax = plt.subplots(figsize=(6, 6))
            wedges, texts, autotexts = ax.pie(
                values,
                labels=labels,
                autopct=lambda pct: f"{pct:.1f}%"
            )
            ax.set_title(f"Gender share (Total Impressions: {grand:,})")
            ax.axis("equal")

            # 保存（一意なファイル名）
            out_path = f"pie_gender_{uuid.uuid4().hex[:8]}.png"
            plt.tight_layout()
            plt.savefig(out_path, dpi=150)
            plt.close(fig)

            # 画像そのものを返却（SwaggerでもDownload表示されます）
            return FileResponse(out_path, media_type="image/png", filename=out_path)
        finally:
            try:
                file.file.close()
            except Exception:
                pass
    # 3) クリエイティブ別 CTR 上位3
    if action == Action.ctr_top3:
        if not file:
            raise HTTPException(status_code=400, detail="file is required for ctr_top3")
        try:
            wrapper = _open_text(file)
            reader = csv.DictReader(wrapper)
            fmap = _normalize_header(reader.fieldnames)
            imp_key = _find_col_fuzzy(fmap, IMP_KEYS, ["imp", "impression", "表示"])
            clk_key = _find_col_fuzzy(fmap, CLK_KEYS, ["click", "クリック"])
            cr_key  = _find_col_fuzzy(fmap, CREATIVE_KEYS, ["creative", "creative name", "ad", "広告", "素材", "クリエ"])
            if not (imp_key and clk_key and cr_key):
                raise HTTPException(status_code=400, detail={
                    "error": "Columns 'creative', 'clicks', or 'impressions' not found",
                    "headers_seen": list(fmap.values())
                })
            rows = []
            for row in reader:
                imps = _safe_int(row.get(imp_key, ""))
                clicks = _safe_int(row.get(clk_key, ""))
                if imps <= 0:
                    continue
                ctr = clicks / imps
                rows.append({
                    "creative": str(row.get(cr_key, "")),
                    "impressions": imps,
                    "clicks": clicks,
                    "ctr": round(ctr, 4),
                })
            rows.sort(key=lambda r: (r["ctr"], r["clicks"], r["impressions"]), reverse=True)
            return {"action": "ctr_top3", "top3": rows[:3]}
        finally:
            try: file.file.close()
            except Exception: pass

    # 4) 文字コード修正（UTF-8 BOMへ）
    if action == Action.fix_encoding:
        if not file:
            raise HTTPException(status_code=400, detail="file is required for fix_encoding")
        try:
            # 読めるエンコーディングを探してテキスト化
            raw = file.file.read()
            text = None
            for enc in ("utf-8-sig", "utf-8", "cp932"):
                try:
                    text = raw.decode(enc)
                    break
                except Exception:
                    continue
            if text is None:
                raise HTTPException(status_code=400, detail="Unsupported input encoding")
            out_path = _unique("converted_utf8_bom.csv")
            with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
                f.write(text)
            return {"action": "fix_encoding", "file": out_path}
        finally:
            try: file.file.close()
            except Exception: pass

    # 5) 1000行ごとに分割（ヘッダーは毎ファイルに付与）
    if action == Action.split_1000:
        if not file:
            raise HTTPException(status_code=400, detail="file is required for split_1000")
        try:
            wrapper = _open_text(file)
            all_rows = list(csv.reader(wrapper))
            if not all_rows:
                raise HTTPException(status_code=400, detail="CSV is empty")
            header, rows = all_rows[0], all_rows[1:]
            chunks = [rows[i:i+1000] for i in range(0, len(rows), 1000)]
            outputs: list[str] = []
            for idx, chunk in enumerate(chunks, start=1):
                path = _unique(f"split_part_{idx}.csv")
                with open(path, "w", encoding="utf-8-sig", newline="") as f:
                    w = csv.writer(f)
                    w.writerow(header)
                    w.writerows(chunk)
                outputs.append(path)
            return {"action": "split_1000", "files": outputs, "parts": len(outputs)}
        finally:
            try: file.file.close()
            except Exception: pass

    # 6) 2CSV結合（ヘッダー一致チェック）
    if action == Action.merge:
        if not (file and file2):
            raise HTTPException(status_code=400, detail="file and file2 are required for merge")
        try:
            w1, w2 = _open_text(file), _open_text(file2)
            r1, r2 = list(csv.reader(w1)), list(csv.reader(w2))
            if not r1 or not r2:
                raise HTTPException(status_code=400, detail="One of the CSVs is empty")
            h1, b1 = r1[0], r1[1:]
            h2, b2 = r2[0], r2[1:]
            if h1 != h2:
                raise HTTPException(status_code=400, detail="CSV headers do not match")
            out_path = _unique("merged.csv")
            with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow(h1)
                w.writerows(b1 + b2)
            return {"action": "merge", "file": out_path, "rows_total": len(b1) + len(b2)}
        finally:
            try:
                file.file.close()
                file2.file.close()
            except Exception:
                pass

    # 未知アクション
    raise HTTPException(status_code=400, detail=f"Unsupported action: {action}")
