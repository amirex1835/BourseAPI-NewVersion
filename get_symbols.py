"""
اسکریپت دریافت اطلاعات تمام نمادهای بورس از BrsApi (Tsetmc/AllSymbols.php)
و ذخیره‌ی خروجی در یک فایل JSON کنار همین اسکریپت.

الگوی درخواست طبق راهنمای API:
https://Api.BrsApi.ir/Tsetmc/AllSymbols.php?key=YourApiKey&type=Number
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

# نوع اوراق طبق جدول راهنما:
# 1 = سهام بورس و فرابورس + صندوق‌های ETF + حق‌تقدم   (پیش‌فرض)
# 2 = بورس کالا (فقط نمادهای موجود در tsetmc)
# 3 = آتی
# 4 = اوراق بدهی
# 5 = تسهیلات مسکن
TYPE = 1

MAX_RETRIES = 5
RETRY_DELAY_SECONDS = 3
TIMEOUT_SECONDS = 30

# مسیر ذخیره خروجی: همان پوشه‌ای که اسکریپت در آن قرار دارد
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "symbols_data.json")


def build_url():
    """ساخت URL دقیقاً بر اساس فرمت راهنما: key و type به‌صورت query string"""
    query = urllib.parse.urlencode({"key": API_KEY, "type": TYPE})
    return f"{BASE_URL}?{query}"


def fetch_all_symbols():
    """
    ارسال درخواست GET به API و بازگرداندن دیتای JSON.
    از urllib استفاده می‌کنیم (بدون نیاز به نصب پکیج requests)
    و در صورت قطع شدن اتصال، چند بار تلاش مجدد می‌کنیم.
    """
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
            print(f"  تلاش {attempt} از {MAX_RETRIES} ...")
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


def save_to_file(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] در حال دریافت اطلاعات نمادها...")
    try:
        data = fetch_all_symbols()
    except Exception as e:
        print(f"خطا در دریافت اطلاعات از API: {e}", file=sys.stderr)
        sys.exit(1)

    save_to_file(data, OUTPUT_FILE)

    count = len(data) if isinstance(data, list) else "نامشخص"
    print(f"تعداد رکورد دریافت‌شده: {count}")
    print(f"اطلاعات با موفقیت در فایل زیر ذخیره شد:\n{OUTPUT_FILE}")


if __name__ == "__main__":
    main()
