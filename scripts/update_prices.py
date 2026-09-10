#!/usr/bin/env python3
import html
import json
import re
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data" / "prices.json"
HK_URL = "https://goldpricexpress.com/jewellery_price/css"
CN_URL = "https://www.jinjia.com.cn/chowsangsang/history.html"
FX_URL = "https://open.er-api.com/v6/latest/HKD"
HEADERS = {"User-Agent": "Mozilla/5.0 gold-price-monitor/1.0"}


def fetch(url):
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read().decode("utf-8", errors="replace")


def text_content(markup):
    clean = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", markup, flags=re.I | re.S)
    clean = re.sub(r"<[^>]+>", " ", clean)
    return re.sub(r"\s+", " ", html.unescape(clean))


def parse_hk(markup, year):
    text = text_content(markup)
    rows = []
    for month, day, price in re.findall(r"(?<!\d)(\d{2})-(\d{2})\s*\$\s*([\d,]+)", text):
        iso = f"{year}-{month}-{day}"
        rows.append({"date": iso, "raw_hkd_tael": int(price.replace(",", ""))})
    return unique(rows)


def parse_cn(markup):
    text = text_content(markup)
    pattern = r"周生生\s*(\d+)元/克.*?(\d{4}-\d{2}-\d{2})"
    rows = [{"date": day, "value": int(price)} for price, day in re.findall(pattern, text)]
    return unique(rows)


def unique(rows):
    result = {}
    for row in rows:
        result.setdefault(row["date"], row)
    return sorted(result.values(), key=lambda row: row["date"])


def merge(old, new, cutoff):
    combined = {row["date"]: row for row in old}
    combined.update({row["date"]: row for row in new})
    return [combined[key] for key in sorted(combined) if key >= cutoff]


def main():
    current = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    today = datetime.now(timezone(timedelta(hours=8))).date()
    cutoff = (today - timedelta(days=40)).isoformat()
    fx = current.get("fx_hkd_cny", 0.8558)
    errors = []
    try:
        fx_data = json.loads(fetch(FX_URL))
        fx = float(fx_data["rates"]["CNY"])
    except Exception as exc:
        errors.append(f"FX: {exc}")
    try:
        hk_new = parse_hk(fetch(HK_URL), today.year)
        if not hk_new:
            raise ValueError("no Hong Kong rows parsed")
    except Exception as exc:
        errors.append(f"HK: {exc}")
        hk_new = []
    try:
        cn_new = parse_cn(fetch(CN_URL))
        if not cn_new:
            raise ValueError("no mainland rows parsed")
    except Exception as exc:
        errors.append(f"CN: {exc}")
        cn_new = []
    hk = merge(current.get("hk", []), hk_new, cutoff)
    cn = merge(current.get("cn", []), cn_new, cutoff)
    for row in hk:
        row["value"] = round(row["raw_hkd_tael"] / 37.5 * fx, 1)
    if not hk or not cn:
        raise SystemExit("No usable price data remains")
    latest = max(hk[-1]["date"], cn[-1]["date"])
    output = {"updated_at": latest, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "fx_hkd_cny": fx, "hk": hk, "cn": cn, "sources": current["sources"]}
    DATA_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if errors:
        print("Completed with fallbacks: " + " | ".join(errors))
    else:
        print(f"Updated through {latest}")


if __name__ == "__main__":
    main()
