"""
NPCI UPI Statewise Data Scraper
================================
Uses undetected-chromedriver to bypass NPCI's bot detection.

Requirements:
    pip install undetected-chromedriver selenium requests python-dateutil openpyxl

Usage:
    python npci_scraper.py
"""

import os
import time
import requests
from datetime import datetime
from dateutil.relativedelta import relativedelta

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────

OUTPUT_DIR     = "npci_statewise_data"
START_DATE     = datetime(2023, 4, 1)
END_DATE       = datetime.today().replace(day=1) - relativedelta(months=1)
NPCI_URL       = "https://www.npci.org.in/product/ecosystem-statistics/upi"
WAIT_TIMEOUT   = 30
DOWNLOAD_DELAY = 4


# ─────────────────────────────────────────────
# BROWSER SETUP
# ─────────────────────────────────────────────

def setup_driver():
    options = uc.ChromeOptions()
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = uc.Chrome(options=options, headless=False)
    return driver


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def get_month_year_list(start, end):
    months, current = [], start
    while current <= end:
        months.append({
            "month_name":  current.strftime("%b"),
            "year_4digit": current.strftime("%Y"),
            "month_num":   current.month,
        })
        current += relativedelta(months=1)
    return months


def file_exists(year_4digit, month_num):
    return os.path.exists(
        os.path.join(OUTPUT_DIR, f"statewise_{year_4digit}_{month_num:02d}.xlsx")
    )


def save_file(url, year_4digit, month_num):
    fname = f"statewise_{year_4digit}_{month_num:02d}.xlsx"
    fpath = os.path.join(OUTPUT_DIR, fname)
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    r.raise_for_status()
    with open(fpath, "wb") as f:
        f.write(r.content)
    return fname


# ─────────────────────────────────────────────
# TAB NAVIGATION
# ─────────────────────────────────────────────

def go_to_statewise_tab(driver, wait):
    tab = wait.until(EC.element_to_be_clickable((
        By.XPATH,
        "//div[@role='tab' and contains(normalize-space(text()),'Statewise')]"
    )))
    driver.execute_script("arguments[0].click();", tab)
    time.sleep(3)
    print("    -> Clicked Statewise tab")


# ─────────────────────────────────────────────
# DROPDOWN INTERACTION
# ─────────────────────────────────────────────

def click_dropdown(driver, wait, dropdown_index, option_text):
    """
    Step 1: Click the toggle button to open the dropdown.
    Step 2: Search the ENTIRE page for the open menu and click the option.
    
    React/Bootstrap sometimes renders the open dropdown-menu outside
    its parent container in the DOM — so we search page-wide after opening.
    """
    # Get all dropdown toggle buttons
    toggles = wait.until(EC.presence_of_all_elements_located((
        By.CSS_SELECTOR,
        "div.dropdown.ecosystem-stat-dropdown-black-arrow button.dropdown-toggle"
    )))

    if dropdown_index >= len(toggles):
        raise ValueError(
            f"Expected toggle index {dropdown_index}, "
            f"only {len(toggles)} found"
        )

    # Click toggle to open
    driver.execute_script("arguments[0].click();", toggles[dropdown_index])
    time.sleep(1.5)

    # Target the open menu specifically — class is 'ecosystem-stat-dropdown show'
    option = wait.until(EC.element_to_be_clickable((
        By.XPATH,
        f"//ul[contains(@class,'ecosystem-stat-dropdown') and contains(@class,'show')]"
        f"//button[normalize-space(text())='{option_text}']"
    )))
    driver.execute_script("arguments[0].click();", option)
    time.sleep(1.5)


# ─────────────────────────────────────────────
# DOWNLOAD + URL INTERCEPTION
# ─────────────────────────────────────────────

def click_download_and_get_url(driver, wait):
    download_div = wait.until(EC.element_to_be_clickable((
        By.CSS_SELECTOR, "div.ecosystem-stat-download"
    )))
    driver.execute_script("arguments[0].click();", download_div)

    # Poll performance log for xlsx URL
    for _ in range(20):
        time.sleep(0.5)
        urls = driver.execute_script(
            "return window.performance.getEntriesByType('resource')"
            ".map(e => e.name)"
            ".filter(n => n.includes('UPI_Statewise') || n.toLowerCase().includes('.xlsx'));"
        )
        if urls:
            return urls[-1]

    return None


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    months = get_month_year_list(START_DATE, END_DATE)
    total  = len(months)

    print(f"\n{'='*55}")
    print(f"  NPCI UPI Statewise Scraper")
    print(f"  Period : {START_DATE.strftime('%b %Y')} -> {END_DATE.strftime('%b %Y')}")
    print(f"  Months : {total}")
    print(f"  Output : {OUTPUT_DIR}/")
    print(f"{'='*55}\n")

    driver = setup_driver()
    wait   = WebDriverWait(driver, WAIT_TIMEOUT)

    print("Loading NPCI page...")
    driver.get(NPCI_URL)
    time.sleep(8)

    go_to_statewise_tab(driver, wait)

    # ── DEBUG: print dropdown structure once before looping ──
    print("\n    [DEBUG] Scanning dropdown structure...")
    try:
        toggles = driver.find_elements(
            By.CSS_SELECTOR,
            "div.dropdown.ecosystem-stat-dropdown-black-arrow button.dropdown-toggle"
        )
        print(f"    [DEBUG] Found {len(toggles)} dropdown toggles")
        for idx, t in enumerate(toggles):
            print(f"      Toggle {idx}: '{t.text.strip()}'")

        # Open first dropdown and inspect what appears
        if toggles:
            driver.execute_script("arguments[0].click();", toggles[0])
            time.sleep(1.5)
            menus = driver.find_elements(By.CSS_SELECTOR, "ul.dropdown-menu, ul.ecosystem-stat-dropdown")
            print(f"    [DEBUG] Dropdown menus visible after click: {len(menus)}")
            for m in menus:
                cls = m.get_attribute("class")
                items = m.find_elements(By.TAG_NAME, "button")
                texts = [b.text.strip() for b in items[:5]]
                print(f"      Menu class='{cls}' | first items: {texts}")
            # Close it again
            driver.execute_script("arguments[0].click();", toggles[0])
            time.sleep(1)
    except Exception as e:
        print(f"    [DEBUG] Error: {e}")
    print()
    # ─────────────────────────────────────────

    downloaded, skipped, failed = 0, 0, []

    for i, m in enumerate(months, 1):
        month_name  = m["month_name"]
        year_4digit = m["year_4digit"]
        month_num   = m["month_num"]
        label       = f"{month_name} {year_4digit}"

        if file_exists(year_4digit, month_num):
            print(f"[{i:02d}/{total}] {label} -- skipping (exists)")
            skipped += 1
            continue

        print(f"[{i:02d}/{total}] {label} -- fetching...", end=" ", flush=True)

        try:
            # Toggle 0 = month, Toggle 1 = year (confirmed from page inspection)
            click_dropdown(driver, wait, 1, year_4digit)
            click_dropdown(driver, wait, 0, month_name)

            url = click_download_and_get_url(driver, wait)

            if url:
                fname = save_file(url, year_4digit, month_num)
                print(f"OK -> {fname}")
                downloaded += 1
            else:
                print("FAIL -> URL not intercepted")
                failed.append(label)

        except Exception as e:
            print(f"FAIL -> {type(e).__name__}: {str(e)[:120]}")
            failed.append(label)

        time.sleep(DOWNLOAD_DELAY)

    driver.quit()

    print(f"\n{'='*55}")
    print(f"  Downloaded : {downloaded}")
    print(f"  Skipped    : {skipped}")
    print(f"  Failed     : {len(failed)}")
    if failed:
        print(f"\n  Retry these manually:")
        for f in failed:
            print(f"    . {f}")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
