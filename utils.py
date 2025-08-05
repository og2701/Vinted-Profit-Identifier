import os
import shutil
import threading
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import config

thread_local = threading.local()
_drivers_for_cleanup = []
_paths_for_cleanup = []
driver_lock = threading.Lock()
log_lock = threading.Lock()

def get_driver():
    driver = getattr(thread_local, 'driver', None)
    if driver is None:
        thread_id = threading.get_ident()
        unique_profile_path = f"{config.CHROME_PROFILE_PATH}-{thread_id}"

        options = Options()
        options.add_argument(f"user-data-dir={unique_profile_path}")
        options.add_argument("profile-directory=Default")
        options.add_argument("--headless")
        options.add_argument("--log-level=3")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        service = Service()
        driver = webdriver.Chrome(service=service, options=options)
        setattr(thread_local, 'driver', driver)
        
        with driver_lock:
            _drivers_for_cleanup.append(driver)
            _paths_for_cleanup.append(unique_profile_path)
    return driver

def cleanup_drivers():
    global _drivers_for_cleanup, _paths_for_cleanup
    with driver_lock:
        for driver in _drivers_for_cleanup:
            try:
                driver.quit()
            except Exception:
                pass
        
        print("\nCleaning up temporary profile directories...")
        for path in _paths_for_cleanup:
            try:
                shutil.rmtree(path)
                print(f" -> Removed: {path}")
            except OSError as e:
                print(f" -> Error removing directory {path}: {e}")
        
        _drivers_for_cleanup = []
        _paths_for_cleanup = []


def log_profit_detailed(item, cex_data, pnl, total_vinted_cost, search_category):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    postage_cost = item.get('postage')
    postage_str = f"£{postage_cost:.2f}" if isinstance(postage_cost, (int, float)) else "N/A"

    scraped_attrs_str = ""
    scraped_attrs = item.get('scraped_attributes', {})
    if scraped_attrs:
        for attr_key, attr_value in scraped_attrs.items():
            scraped_attrs_str += f"      - {attr_key}: {attr_value}\n"
    if not scraped_attrs_str:
        scraped_attrs_str = "      (No additional attributes found)\n"

    description_output = ""
    if item.get('description'):
        description_output = f"  -> Description: {item['description'][:100]}...\n"

    log_entry = f"""
--- Potential Profit Found [{timestamp}] ---
Search Category: {search_category}
Vinted item: {item['title']}
  -> Price: £{item['price']:.2f}, Postage: {postage_str}
  -> Link to buy: {item['link']}
  -> Scraped Attributes:
{scraped_attrs_str.strip()}
{description_output.strip()}
  -> CeX webuy price: £{cex_data['price']:.2f}
  -> CeX sell page: {cex_data['link']}
  -> Total Vinted cost (inc. fees): ~£{total_vinted_cost:.2f}
  ✅ Potential profit: £{pnl:.2f}
------------------------------------
"""
    with log_lock:
        with open(config.PROFIT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_entry)
