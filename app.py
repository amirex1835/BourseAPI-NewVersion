"""
بک‌اند پنل مانیتورینگ پیش‌گشایش (تک فایل)

نکته‌ی مهم: تمام منطق، فرمول‌ها و شرط‌ها دقیقاً همون چیزیه که توی
preopening_check.py تایید و نهایی شده بود. هیچ عدد یا شرطی اینجا
تغییر نکرده - فقط به‌جای print کردن نتیجه توی کنسول، نتیجه رو به
شکل JSON از طریق یه API برمی‌گردونیم تا index.html نشونش بده.

اجرا:
    pip install flask
    python app.py
    مرورگر -> http://127.0.0.1:5000

فایل symbols_data.json (خروجی get_symbols.py) باید کنار همین app.py باشه.
"""

import json
import os
import sys
import threading
import time
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime

from flask import Flask, jsonify, send_from_directory

# ---- تنظیمات (دقیقاً همون مقادیر preopening_check.py) ----
API_KEY = "B5zgBWpp87rDlVHmL6Rx963abdhRaNhT"
BASE_URL = "https://Api.BrsApi.ir/Tsetmc/AllSymbols.php"
TYPE = 1

MAX_RETRIES = 5
RETRY_DELAY_SECONDS = 3
TIMEOUT_SECONDS = 30

# فاصله زمانی بین هر بار اجرای مجدد بررسی (به ثانیه) - همینجا دستی تنظیم کن
LOOP_INTERVAL_SECONDS = 10

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
YESTERDAY_FILE = os.path.join(SCRIPT_DIR, "symbols_data.json")

EXCLUDED_LAST_DIGITS = {"2", "3", "۲", "۳"}
EXCLUDED_INDUSTRY_GROUPS = {"صندوق سرمایه‌گذاری قابل معامله", "صندوق سرمایه گذاری قابل معامله"}
MIN_PRICE_GAP_PERCENT = 0.003


# ---------------------------------------------------------------------
# دریافت دیتای زنده امروز از API (عیناً از preopening_check.py)
# ---------------------------------------------------------------------
def build_url():
    query = urllib.parse.urlencode({"key": API_KEY, "type": TYPE})
    return f"{BASE_URL}?{query}"


def fetch_today_live_data():
    url = build_url()
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
        },
    )

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                raw_data = response.read().decode("utf-8")
                return json.loads(raw_data)
        except (urllib.error.URLError, urllib.error.HTTPError, ConnectionResetError,
                TimeoutError, json.JSONDecodeError) as e:
            last_error = e
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SECONDS)

    raise last_error


def load_yesterday_data(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def to_number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def is_excluded_symbol(symbol_name):
    if not symbol_name:
        return False
    return symbol_name.strip()[-1] in EXCLUDED_LAST_DIGITS


def is_excluded_industry_group(industry_group):
    if not industry_group:
        return False
    return industry_group.strip() in EXCLUDED_INDUSTRY_GROUPS


# ---------------------------------------------------------------------
# یک بار اجرای کامل بررسی - عیناً همون منطق preopening_check.py، فقط
# به‌جای print، نتیجه رو برمی‌گردونه (return) تا ذخیره و سرو بشه
# ---------------------------------------------------------------------
def run_check(yesterday_map):
    today_data = fetch_today_live_data()

    if not isinstance(today_data, list):
        raise ValueError("ساختار دیتای امروز درست نیست.")

    total_checked = 0
    excluded_count = 0
    excluded_etf_count = 0
    matched = []

    for today_item in today_data:
        symbol = today_item.get("l18", "")

        if is_excluded_symbol(symbol):
            excluded_count += 1
            continue

        if is_excluded_industry_group(today_item.get("cs")):
            excluded_etf_count += 1
            continue

        yesterday_item = yesterday_map.get(symbol)
        if yesterday_item is None:
            continue

        total_checked += 1

        pc_yesterday = to_number(yesterday_item.get("pc"))
        pl_yesterday = to_number(yesterday_item.get("pl"))
        plc_yesterday = to_number(yesterday_item.get("plc"))
        pcc_yesterday = to_number(yesterday_item.get("pcc"))
        plp_yesterday = to_number(yesterday_item.get("plp"))
        pcp_yesterday = to_number(yesterday_item.get("pcp"))
        po1_today = to_number(today_item.get("po1"))

        if (pc_yesterday is None or pl_yesterday is None or plc_yesterday is None
                or pcc_yesterday is None or plp_yesterday is None or pcp_yesterday is None
                or po1_today is None or po1_today <= 0 or pc_yesterday <= 0):
            continue

        price_gap = plc_yesterday - pcc_yesterday
        price_gap_percent = plp_yesterday - pcp_yesterday
        condition_1 = price_gap > 0 and price_gap_percent >= (MIN_PRICE_GAP_PERCENT * 100)
        condition_2 = po1_today < pc_yesterday

        if condition_1 and condition_2:
            matched.append({
                "symbol": symbol,
                "name": today_item.get("l30", "-"),
                "pc_yesterday": pc_yesterday,
                "pl_yesterday": pl_yesterday,
                "po1_today": po1_today,
                "price_gap": price_gap,
                "price_gap_percent": price_gap_percent,
            })

    matched.sort(key=lambda m: m["price_gap_percent"], reverse=True)

    return {
        "matches": matched,
        "stats": {
            "total_checked": total_checked,
            "excluded_digit_count": excluded_count,
            "excluded_etf_count": excluded_etf_count,
            "matched_count": len(matched),
        },
    }


# ---------------------------------------------------------------------
# وضعیت مشترک بین لوپ پس‌زمینه و درخواست‌های API (thread-safe)
# ---------------------------------------------------------------------
state_lock = threading.Lock()
shared_state = {
    "status": "starting",       # starting | ok | error | no_yesterday_file
    "error_message": None,
    "last_update": None,
    "loop_interval_seconds": LOOP_INTERVAL_SECONDS,
    "matches": [],
    "stats": None,
}


def background_loop():
    yesterday_data = load_yesterday_data(YESTERDAY_FILE)

    if not isinstance(yesterday_data, list):
        with state_lock:
            shared_state["status"] = "no_yesterday_file"
            shared_state["error_message"] = (
                "فایل symbols_data.json پیدا نشد یا معتبر نیست. "
                "باید اون رو کنار app.py قرار بدی."
            )
        return

    yesterday_map = {item.get("l18"): item for item in yesterday_data if item.get("l18")}

    while True:
        try:
            result = run_check(yesterday_map)
            with state_lock:
                shared_state["status"] = "ok"
                shared_state["error_message"] = None
                shared_state["last_update"] = datetime.now().isoformat()
                shared_state["matches"] = result["matches"]
                shared_state["stats"] = result["stats"]
        except Exception as e:
            with state_lock:
                shared_state["status"] = "error"
                shared_state["error_message"] = str(e)

        time.sleep(LOOP_INTERVAL_SECONDS)


# ---------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------
app = Flask(__name__, static_folder=None)


@app.route("/api/latest")
def api_latest():
    with state_lock:
        return jsonify(dict(shared_state))


@app.route("/")
def serve_index():
    return send_from_directory(SCRIPT_DIR, "index.html")


if __name__ == "__main__":
    worker = threading.Thread(target=background_loop, daemon=True)
    worker.start()
    print("سرور روی http://127.0.0.1:5000 بالا اومد")
    app.run(host="127.0.0.1", port=5000, debug=False)
