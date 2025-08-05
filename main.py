import concurrent.futures
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import config
from scraper import scrape_vinted_search_page, process_item
from utils import cleanup_drivers, print_and_log

def main():
    for term in config.SEARCH_TERMS:
        search_page_driver = None
        items_to_process = []
        try:
            print_and_log(f"\n--- Scraping Vinted for: '{term}' ---")
            
            service = Service()
            options = Options()
            options.add_argument("--headless")
            options.add_argument("--log-level=3")
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
            search_page_driver = webdriver.Chrome(service=service, options=options)
            
            items_to_process = scrape_vinted_search_page(search_page_driver, term, num_items_to_check=config.ITEMS_TO_CHECK_PER_TERM)
            
            if not items_to_process:
                print_and_log("No items found to process. Moving to the next search term.")
                continue

            print_and_log(f"Found {len(items_to_process)} items to analyse. Starting parallel processing...")
            
        except Exception as e:
            print_and_log(f"An error occurred while setting up the search for '{term}': {e}")
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
                            print_and_log(f"A task in the thread pool generated an exception: {e}")
            finally:
                print_and_log(f"\n--- Finished processing for '{term}' ---")
                cleanup_drivers()
                print_and_log("\n" + "="*50 + "\n")

if __name__ == "__main__":
    main()
