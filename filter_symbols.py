"""
اسکریپت خواندن فایل symbols_data.json و فیلتر سهامی که:
    قیمت پایانی (pc) کمتر از آخرین قیمت معامله (pl) بوده باشد.

خروجی: لیست نمادهای واجد شرط + آمار (تعداد کل / تعداد واجد شرط)
"""

import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE = os.path.join(SCRIPT_DIR, "symbols_data.json")


def load_symbols(path):
    if not os.path.exists(path):
        print(f"فایل {path} پیدا نشد. اول اسکریپت get_symbols.py رو اجرا کن.", file=sys.stderr)
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def to_number(value):
    """تبدیل امن مقدار به عدد؛ اگر نشد None برمی‌گردونه"""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ارقامی که نماد نباید به آن‌ها ختم شود (هم انگلیسی هم فارسی، برای اطمینان)
EXCLUDED_LAST_DIGITS = {"2", "3", "۲", "۳"}


def is_excluded_symbol(symbol_name):
    """اگر نماد به رقم 2 یا 3 ختم بشه (مثل وبملت3) True برمی‌گردونه"""
    if not symbol_name:
        return False
    return symbol_name.strip()[-1] in EXCLUDED_LAST_DIGITS


def main():
    data = load_symbols(INPUT_FILE)

    if not isinstance(data, list):
        print("ساختار فایل JSON لیست نیست، بررسی کن که فایل درست ذخیره شده باشه.", file=sys.stderr)
        sys.exit(1)

    total_count = len(data)
    excluded_count = 0
    matched = []

    for item in data:
        symbol = item.get("l18", "")

        # حذف نمادهایی که آخرشون به 2 یا 3 ختم میشه (مثل وبملت3)
        if is_excluded_symbol(symbol):
            excluded_count += 1
            continue

        pc = to_number(item.get("pc"))   # قیمت پایانی
        pl = to_number(item.get("pl"))   # آخرین قیمت معامله

        if pc is None or pl is None:
            continue  # رکورد ناقص، ردش کن

        if pc < pl:
            matched.append(item)

    print("سهم‌هایی که قیمت پایانی‌شون کمتر از آخرین قیمت معامله بوده:\n")
    for item in matched:
        symbol = item.get("l18", "-")
        name = item.get("l30", "-")
        pc = item.get("pc", "-")
        pl = item.get("pl", "-")
        print(f"نماد: {symbol:<10} | نام: {name:<25} | قیمت پایانی: {pc:<10} | آخرین قیمت: {pl}")

    print("\n----------------------------------------")
    print(f"تعداد کل سهم‌های خونده‌شده: {total_count}")
    print(f"تعداد سهم‌های حذف‌شده (آخرشون 2 یا 3): {excluded_count}")
    print(f"تعداد سهم‌هایی که این شرط رو داشتن: {len(matched)}")


if __name__ == "__main__":
    main()
