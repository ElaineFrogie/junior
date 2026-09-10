#!/usr/bin/env python3
import html
import json
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data" / "prices.json"
HK_URL = "https://goldpricexpress.com/jewellery_price/css"
CN_URL = "https://www.jinjia.com.cn/chowsangsang/history.html"
FX_URL = "https://open.er-api.com/v6/latest/HKD"
JP_URL = "https://gold.tanaka.co.jp/commodity/souba/english/index.php"
JP_HISTORY_URL = "https://gold.tanaka.co.jp/commodity/souba/d-gold_recent.php"
KR_URL = "https://www.kaggold.com/sub01/sub01.php"
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


def parse_jp(markup):
    text = text_content(markup)
    stamp = re.search(r"As of at\s+(\d{1,2}:\d{2})\s+on\s+([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?,\s+(\d{4})", text, re.I)
    price = re.search(r"GOLD\s+([\d,]+)\s+yen", text, re.I)
    if not stamp or not price:
        return []
    published = datetime.strptime(f"{stamp.group(2)} {stamp.group(3)} {stamp.group(4)}", "%B %d %Y")
    return [{"date": published.date().isoformat(), "source_time": stamp.group(1), "raw_jpy_g": int(price.group(1).replace(",", ""))}]


class TableRows(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.row, self.cell = [], None, None

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "tr":
            self.row = []
        elif tag.lower() in ("td", "th") and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag.lower() in ("td", "th") and self.cell is not None:
            self.row.append(" ".join(self.cell).strip())
            self.cell = None
        elif tag.lower() == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None


def parse_jp_history(markup, year):
    parser = TableRows()
    parser.feed(markup)
    rows = []
    for cells in parser.rows:
        if len(cells) < 2 or not re.fullmatch(r"\d{2}\.\d{2}", cells[0]):
            continue
        price = re.search(r"[\d,]+", cells[1])
        if not price:
            continue
        month, day = cells[0].split(".")
        row_year = year - 1 if int(month) > datetime.now().month + 2 else year
        rows.append({"date": f"{row_year}-{month}-{day}", "raw_jpy_g": int(price.group().replace(",", ""))})
    return unique(rows)


def parse_kr(markup):
    text = text_content(markup)
    stamp = re.search(r"금시세\s+(\d{4})[.-](\d{2})[.-](\d{2})\s+기준", text)
    price = re.search(r"24K\s+([\d,]+)원", text)
    if not stamp or not price:
        return []
    return [{"date": "-".join(stamp.groups()), "source_time": None, "raw_krw_3_75g": int(price.group(1).replace(",", ""))}]


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
    rates = current.get("fx_rates", {"CNY": current.get("fx_hkd_cny", 0.8558), "JPY": 19.56, "KRW": 170.5})
    errors = []
    try:
        fx_data = json.loads(fetch(FX_URL))
        rates = {code: float(fx_data["rates"][code]) for code in ("CNY", "JPY", "KRW")}
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
    try:
        jp_new = unique(parse_jp_history(fetch(JP_HISTORY_URL), today.year) + parse_jp(fetch(JP_URL)))
        if not jp_new:
            raise ValueError("no Japan rows parsed")
    except Exception as exc:
        errors.append(f"JP: {exc}")
        jp_new = []
    try:
        kr_new = parse_kr(fetch(KR_URL))
        if not kr_new:
            raise ValueError("no Korea rows parsed")
    except Exception as exc:
        errors.append(f"KR: {exc}")
        kr_new = []
    hk = merge(current.get("hk", []), hk_new, cutoff)
    cn = merge(current.get("cn", []), cn_new, cutoff)
    jp = merge(current.get("jp", []), jp_new, cutoff)
    kr = merge(current.get("kr", []), kr_new, cutoff)
    for row in hk:
        row["value"] = round(row["raw_hkd_tael"] / 37.5 * rates["CNY"], 1)
    for row in jp:
        row["value"] = round(row["raw_jpy_g"] * rates["CNY"] / rates["JPY"], 1)
    for row in kr:
        row["value"] = round(row["raw_krw_3_75g"] / 3.75 * rates["CNY"] / rates["KRW"], 1)
    if not hk or not cn or not jp or not kr:
        raise SystemExit("No usable price data remains")
    latest = max(hk[-1]["date"], cn[-1]["date"], jp[-1]["date"], kr[-1]["date"])
    generated = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="minutes")
    sources = dict(current["sources"])
    sources["jp_history"] = JP_HISTORY_URL
    output = {"updated_at": latest, "generated_at": generated, "fx_hkd_cny": rates["CNY"], "fx_rates": rates, "hk": hk, "cn": cn, "jp": jp, "kr": kr, "sources": sources}
    DATA_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if errors:
        print("Completed with fallbacks: " + " | ".join(errors))
    else:
        print(f"Updated through {latest}")


if __name__ == "__main__":
    main()
