import concurrent.futures
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import config
from scraper import scrape_vinted_search_page, process_item
from utils import cleanup_drivers

def main():
    for term in config.SEARCH_TERMS:
        search_page_driver = None
        items_to_process = []
        try:
            print(f"\n--- Scraping Vinted for: '{term}' ---")
            
            service = Service()
            options = Options()
            options.add_argument("--headless")
            options.add_argument("--log-level=3")
            search_page_driver = webdriver.Chrome(service=service, options=options)
            
            items_to_process = scrape_vinted_search_page(search_page_driver, term, num_items_to_check=config.ITEMS_TO_CHECK_PER_TERM)
            
            if not items_to_process:
                print("No items found to process. Moving to the next search term.")
                continue

            print(f"Found {len(items_to_process)} items to analyse. Starting parallel processing...")
            
        finally:
            if search_page_driver:
                search_page_driver.quit()

        if items_to_process:
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=config.MAX_WORKERS) as executor:
                    futures = [executor.submit(process_item, item, term) for item in items_to_process]
                    
                    for future in concurrent.futures.as_completed(futures):
                        try:
                            future.result()
                        except Exception as e:
                            print(f"A task in the thread pool generated an exception: {e}")
            finally:
                print(f"\n--- Finished processing for '{term}' ---")
                cleanup_drivers()
                print("\n" + "="*50 + "\n")

if __name__ == "__main__":
    main()
