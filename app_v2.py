"""
بک‌اند پنل مانیتورینگ پیش‌گشایش (تک فایل) - نسخه ۲

تفاوت این نسخه با نسخه‌ی قبلی (app.py):
    فاصله‌ی پایانی و آخرین معامله‌ی دیروز، به‌جای استفاده از فیلدهای
    plc/pcc/plp/pcp، مستقیماً از خود pl و pc محاسبه میشه:

        price_gap = pl - pc
        price_gap_percent = (pl - pc) / pc * 100

    دلیل: فیلدهای plc/plp/pcc/pcp گاهی تا مدتی بعد از بسته شدن بازار
    هنوز صفر هستن (اگه get_symbols.py رو زود بعد از بسته شدن بازار یا
    نزدیک صبح روز بعد اجرا کنی). ولی pl و pc همیشه مقدار معتبر دارن،
    پس این روش مستقل از ساعت اجرای get_symbols.py درست کار می‌کنه.

    بقیه‌ی منطق (فیلتر رقم آخر، فیلتر ETF، شرط دوم بر اساس po1) هیچ
    تغییری نکرده.

اجرا:
    pip install flask
    python app_v2.py
    مرورگر -> http://127.0.0.1:5000

فایل symbols_data.json (خروجی get_symbols.py) باید کنار همین فایل باشه.
"""

import json
import os
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
MIN_PRICE_GAP_PERCENT = 0.001  # 0.3%


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
    """نمادهایی که به رقم 2 یا 3 ختم میشن (مثل وبملت3) حذف میشن"""
    if not symbol_name:
        return False
    return symbol_name.strip()[-1] in EXCLUDED_LAST_DIGITS


def is_excluded_industry_group(industry_group):
    """نمادهایی که گروه صنعتشون صندوق سرمایه‌گذاری قابل معامله (ETF) هست حذف میشن"""
    if not industry_group:
        return False
    return industry_group.strip() in EXCLUDED_INDUSTRY_GROUPS


# ---------------------------------------------------------------------
# یک بار اجرای کامل بررسی - منطق عیناً از preopening_check.py، فقط
# خروجی به‌جای print، به شکل دو لیست (شرط اول / هر دو شرط) برگردونده میشه
# ---------------------------------------------------------------------
def run_check(yesterday_map):
    today_data = fetch_today_live_data()

    if not isinstance(today_data, list):
        raise ValueError("ساختار دیتای امروز درست نیست.")

    total_checked = 0
    excluded_count = 0
    excluded_etf_count = 0

    condition1_list = []       # فقط شرط اول
    both_conditions_list = []  # شرط اول + شرط دوم

    for today_item in today_data:
        symbol = today_item.get("l18", "")

        # حذف نمادهایی که آخرشون 2 یا 3 هست
        if is_excluded_symbol(symbol):
            excluded_count += 1
            continue

        # حذف نمادهایی که گروه صنعتشون صندوق سرمایه‌گذاری قابل معامله (ETF) هست
        if is_excluded_industry_group(today_item.get("cs")):
            excluded_etf_count += 1
            continue

        yesterday_item = yesterday_map.get(symbol)
        if yesterday_item is None:
            continue  # این نماد دیروز دیتا نداشته

        total_checked += 1

        pc_yesterday = to_number(yesterday_item.get("pc"))    # قیمت پایانی دیروز
        pl_yesterday = to_number(yesterday_item.get("pl"))    # آخرین قیمت معامله دیروز
        po1_today = to_number(today_item.get("po1"))          # قیمت سفارش فروش سطر اول امروز

        if pc_yesterday is None or pl_yesterday is None:
            continue  # دیتای دیروز ناقصه، اصلا نمیشه شرط اول رو چک کرد

        if pc_yesterday <= 0:
            continue  # برای جلوگیری از تقسیم بر صفر

        # شرط اول: پایانی دیروز باید کمتر از آخرین معامله دیروز باشه، ضمن
        # اینکه فاصله‌شون هم باید حداقل MIN_PRICE_GAP_PERCENT (0.3%) باشه.
        #
        # نکته‌ی مهم: فاصله رو مستقیماً از خود pl و pc حساب می‌کنیم، نه از
        # فیلدهای plc/pcc/plp/pcp. دلیلش اینه که pl و pc همیشه (هر ساعتی
        # از شبانه‌روز که get_symbols.py رو اجرا کنی) مقدار معتبر دارن، ولی
        # فیلدهای plc/plp/pcc/pcp گاهی تا مدتی بعد از بسته شدن بازار هنوز
        # صفر هستن (هنوز توسط سرور محاسبه نشدن). با این روش، مهم نیست چه
        # ساعتی get_symbols.py رو اجرا کرده باشی - نتیجه همیشه درسته.
        # این فاصله‌ی درصدی هم دقیقاً نسبت به pc حساب میشه (نه نسبت به py)،
        # که دقیقاً همون تعریف اصلی مدنظرمون بود.
        price_gap = pl_yesterday - pc_yesterday
        price_gap_percent = (price_gap / pc_yesterday) * 100
        condition_1 = price_gap > 0 and price_gap_percent >= (MIN_PRICE_GAP_PERCENT * 100)

        if not condition_1:
            continue  # اگه شرط اول نبود، نه در لیست اول نه در لیست دوم جایی داره

        condition1_list.append({
            "symbol": symbol,
            "price_gap_percent": price_gap_percent,
        })

        # شرط دوم: قیمت سفارش فروش سطر اول امروز کمتر از قیمت پایانی دیروز.
        # po1 برابر با صفر یعنی هنوز سفارش فروشی ثبت نشده (دیتای نامعتبر
        # برای این شرط) - این حالت رو نادیده می‌گیریم، وگرنه چون 0 از هر
        # عددی کمتره، شرط دوم به‌اشتباه همیشه True میشه.
        if po1_today is not None and po1_today > 0 and pc_yesterday > 0:
            condition_2 = po1_today < pc_yesterday
            if condition_2:
                both_conditions_list.append({
                    "symbol": symbol,
                    "price_gap_percent": price_gap_percent,
                })

    # سورت نزولی بر اساس فاصله‌ی درصدی: بیشترین فاصله اول
    condition1_list.sort(key=lambda m: m["price_gap_percent"], reverse=True)
    both_conditions_list.sort(key=lambda m: m["price_gap_percent"], reverse=True)

    return {
        "condition1_list": condition1_list,
        "both_conditions_list": both_conditions_list,
        "stats": {
            "total_checked": total_checked,
            "excluded_digit_count": excluded_count,
            "excluded_etf_count": excluded_etf_count,
            "condition1_count": len(condition1_list),
            "both_conditions_count": len(both_conditions_list),
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
    "condition1_list": [],
    "both_conditions_list": [],
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
                shared_state["condition1_list"] = result["condition1_list"]
                shared_state["both_conditions_list"] = result["both_conditions_list"]
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
