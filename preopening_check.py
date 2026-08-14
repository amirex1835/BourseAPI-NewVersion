"""
اسکریپت بررسی سهام مناسب خرید در بازه پیش‌گشایش (۸:۴۵ تا ۹:۰۰)

منطق کار:
    ۱. دیتای دیروز از فایل symbols_data.json خونده میشه (که عصر دیروز
       با اسکریپت get_symbols.py ذخیره شده). از این دیتا فقط pc (قیمت
       پایانی دیروز) و pl (آخرین قیمت معامله دیروز) لازم داریم.
    ۲. دیتای زنده‌ی امروز مستقیم از API گرفته میشه (چون توی بازه
       پیش‌گشایش، سفارش‌های خرید/فروش هر لحظه در حال تغییرن). از این
       دیتا فقط po1 (قیمت سفارش فروش سطر اول) لازم داریم.
    ۳. نمادهایی که آخرشون به رقم 2 یا 3 ختم میشه، حذف میشن.
    ۴. برای هر نماد، دو دیتای دیروز و امروز بر اساس نماد (l18) به هم
       وصل (match) میشن.
    ۵. شرط اول: pc دیروز < pl دیروز
       شرط دوم : po1 امروز < pc دیروز
       اگه هر دو شرط همزمان برقرار بود، نماد پرینت میشه.

خروجی: لیست نمادهای واجد شرط + تعداد کل بررسی‌شده‌ها و تعداد واجدین شرط
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime

# ---- تنظیمات ----
API_KEY = "B5zgBWpp87rDlVHmL6Rx963abdhRaNhT"
BASE_URL = "https://Api.BrsApi.ir/Tsetmc/AllSymbols.php"
TYPE = 1

MAX_RETRIES = 5
RETRY_DELAY_SECONDS = 3
TIMEOUT_SECONDS = 30

# فاصله زمانی بین هر بار اجرای مجدد بررسی (به ثانیه) - همینجا دستی تنظیم کن
LOOP_INTERVAL_SECONDS = 20

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
YESTERDAY_FILE = os.path.join(SCRIPT_DIR, "symbols_data.json")  # دیتای ذخیره‌شده‌ی دیروز

# ارقامی که نماد نباید به آن‌ها ختم شود (هم انگلیسی هم فارسی)
EXCLUDED_LAST_DIGITS = {"2", "3", "۲", "۳"}

# نام گروه صنعتی که باید کاملاً حذف بشه (فیلد cs در دیتای API)
EXCLUDED_INDUSTRY_GROUPS = {"صندوق سرمایه‌گذاری قابل معامله", "صندوق سرمایه گذاری قابل معامله"}

# حداقل درصد فاصله‌ی مجاز بین آخرین قیمت معامله و قیمت پایانی دیروز (0.3%)
MIN_PRICE_GAP_PERCENT = 0.003


# ---------------------------------------------------------------------
# بخش دریافت دیتای زنده‌ی امروز از API (مشابه get_symbols.py)
# ---------------------------------------------------------------------
def build_url():
    query = urllib.parse.urlencode({"key": API_KEY, "type": TYPE})
    return f"{BASE_URL}?{query}"


def fetch_today_live_data():
    """دریافت دیتای زنده‌ی امروز (شامل po1 و بقیه سفارش‌ها) از API"""
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
            print(f"  دریافت دیتای زنده امروز - تلاش {attempt} از {MAX_RETRIES} ...")
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                raw_data = response.read().decode("utf-8")
                return json.loads(raw_data)
        except (urllib.error.URLError, urllib.error.HTTPError, ConnectionResetError,
                TimeoutError, json.JSONDecodeError) as e:
            last_error = e
            print(f"  خطا در تلاش {attempt}: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SECONDS)

    raise last_error


# ---------------------------------------------------------------------
# بخش خواندن دیتای دیروز از فایل ذخیره‌شده
# ---------------------------------------------------------------------
def load_yesterday_data(path):
    if not os.path.exists(path):
        print(f"فایل {path} پیدا نشد. اول اسکریپت get_symbols.py رو (عصر دیروز) اجرا کن.",
              file=sys.stderr)
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------
# توابع کمکی
# ---------------------------------------------------------------------
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
# یک بار اجرای کامل بررسی (دریافت دیتای زنده + مقایسه + پرینت نتایج)
# ---------------------------------------------------------------------
def run_check(yesterday_map):
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] اجرای بررسی جدید...\n")

    # دریافت دیتای زنده‌ی امروز
    try:
        today_data = fetch_today_live_data()
    except Exception as e:
        print(f"خطا در دریافت دیتای زنده امروز: {e}", file=sys.stderr)
        return

    if not isinstance(today_data, list):
        print("ساختار دیتای امروز درست نیست.", file=sys.stderr)
        return

    total_checked = 0
    excluded_count = 0
    excluded_etf_count = 0
    matched = []

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
            continue  # این نماد دیروز دیتا نداشته (نماد جدید یا غیرفعال)

        total_checked += 1

        pc_yesterday = to_number(yesterday_item.get("pc"))   # قیمت پایانی دیروز
        pl_yesterday = to_number(yesterday_item.get("pl"))   # آخرین قیمت معامله دیروز
        plc_yesterday = to_number(yesterday_item.get("plc")) # تغییر مقداری آخرین قیمت دیروز (pl - py)
        pcc_yesterday = to_number(yesterday_item.get("pcc")) # تغییر مقداری قیمت پایانی دیروز (pc - py)
        po1_today = to_number(today_item.get("po1"))         # قیمت سفارش فروش سطر اول امروز

        # po1 برابر با صفر یعنی در حال حاضر سفارش فروشی روی نماد ثبت نشده
        # (مثلاً خارج از بازه پیش‌گشایش هستیم یا صف فروش خالیه) - این حالت
        # دیتای معتبر برای مقایسه نیست و باید ردش کنیم، وگرنه چون 0 از هر
        # عددی کمتره، شرط دوم به‌اشتباه همیشه True میشه.
        if (pc_yesterday is None or pl_yesterday is None or plc_yesterday is None
                or pcc_yesterday is None or po1_today is None
                or po1_today <= 0 or pc_yesterday <= 0):
            continue  # دیتای ناقص یا سفارش فروش ثبت‌نشده

        # شرط اول: پایانی دیروز باید کمتر از آخرین معامله دیروز باشه، ضمن
        # اینکه فاصله‌شون هم باید حداقل MIN_PRICE_GAP_PERCENT (0.3%) باشه.
        # به‌جای محاسبه‌ی دستی (pl - pc)، از فیلدهای آماده‌ی خود API استفاده
        # می‌کنیم: چون plc = pl - py و pcc = pc - py، تفریق‌شون (plc - pcc)
        # دقیقاً برابر pl - pc هست (py حذف میشه) و همون عدد دقیق رو میده،
        # بدون نیاز به محاسبه‌ی جدا از pl و pc.
        price_gap = plc_yesterday - pcc_yesterday  # دقیقاً برابر pl_yesterday - pc_yesterday
        price_gap_percent = price_gap / pc_yesterday
        condition_1 = price_gap > 0 and price_gap_percent >= MIN_PRICE_GAP_PERCENT
        # شرط دوم: قیمت سفارش فروش سطر اول امروز کمتر از قیمت پایانی دیروز
        condition_2 = po1_today < pc_yesterday

        if condition_1 and condition_2:
            matched.append({
                "symbol": symbol,
                "name": today_item.get("l30", "-"),
                "pc_yesterday": pc_yesterday,
                "pl_yesterday": pl_yesterday,
                "po1_today": po1_today,
            })

    # چاپ نتایج
    print("سهم‌های واجد شرط خرید در پیش‌گشایش:\n")
    for m in matched:
        print(
            f"نماد: {m['symbol']:<10} | نام: {m['name']:<25} | "
            f"پایانی دیروز: {m['pc_yesterday']:<10} | "
            f"آخرین معامله دیروز: {m['pl_yesterday']:<10} | "
            f"po1 امروز: {m['po1_today']}"
        )

    print("\n----------------------------------------")
    print(f"تعداد کل سهم‌های بررسی‌شده (بعد از حذف نمادهای 2/3 و ETF): {total_checked}")
    print(f"تعداد نمادهای حذف‌شده (آخرشون 2 یا 3): {excluded_count}")
    print(f"تعداد نمادهای حذف‌شده (گروه صندوق ETF): {excluded_etf_count}")
    print(f"تعداد سهم‌هایی که هر دو شرط رو داشتن: {len(matched)}")


# ---------------------------------------------------------------------
# منطق اصلی: دیتای دیروز فقط یک بار خونده میشه، بعد لوپ بی‌نهایت
# هر LOOP_INTERVAL_SECONDS ثانیه دوباره دیتای زنده رو می‌گیره و بررسی می‌کنه
# ---------------------------------------------------------------------
def main():
    # دیتای دیروز فقط یک بار لازمه خونده بشه (تغییر نمی‌کنه)
    yesterday_data = load_yesterday_data(YESTERDAY_FILE)
    if not isinstance(yesterday_data, list):
        print("ساختار فایل دیروز درست نیست.", file=sys.stderr)
        sys.exit(1)

    yesterday_map = {item.get("l18"): item for item in yesterday_data if item.get("l18")}

    print(f"شروع مانیتورینگ - هر {LOOP_INTERVAL_SECONDS} ثانیه یک‌بار بررسی می‌شه.")
    print("برای توقف، Ctrl+C رو بزن.\n")

    try:
        while True:
            run_check(yesterday_map)
            print(f"\n--- {LOOP_INTERVAL_SECONDS} ثانیه صبر می‌کنیم تا بررسی بعدی ---")
            time.sleep(LOOP_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("\nمانیتورینگ متوقف شد.")


if __name__ == "__main__":
    main()
