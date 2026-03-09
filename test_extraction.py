import sys
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import scraper
import utils

def main():
    if len(sys.argv) > 1:
        test_link = sys.argv[1]
    else:
        test_link = 'https://www.vinted.co.uk/items/3588961726-ps5-hogwarts-legacy'
        
    print(f"Testing extraction on Vinted item: {test_link}")
    
    start_time = time.time()
    
    service = Service()
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--log-level=3")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(service=service, options=options)
    
    test_item = {
        'link': test_link
    }
    
    setattr(utils.thread_local, 'driver', driver)
    
    try:
        # Pass a generic testing category if none provided
        scraper.process_item(test_item, "Test Category")
        print(f"\nTime taken: {time.time() - start_time:.2f} seconds")
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
