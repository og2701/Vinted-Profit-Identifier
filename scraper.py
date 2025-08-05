import os
import re
import time
from openai import OpenAI
from dotenv import load_dotenv
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    StaleElementReferenceException,
    WebDriverException
)
from urllib3.exceptions import MaxRetryError, NewConnectionError

from utils import get_driver, log_profit_detailed

def generate_cex_query_from_vinted_listing(vinted_item_details, category, log_messages):
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        log_messages.append("-> ERROR: OPENAI_API_KEY not found in .env file. Using item title as fallback.")
        return vinted_item_details.get('title', 'N/A')

    title = vinted_item_details.get('title', '')
    description = vinted_item_details.get('description', '')
    
    attributes_str = ""
    scraped_attributes = vinted_item_details.get('scraped_attributes', {})
    for key, value in scraped_attributes.items():
        attributes_str += f"- {key}: {value}\n"
    if not attributes_str:
        attributes_str = "No additional attributes found."

    try:
        client = OpenAI(api_key=api_key)
        prompt = f"""
        From the following Vinted product title, description, and additional scraped attributes, generate a concise search query for the CeX website.
        - The query should be the core product name, model, and any other critical, specific identifiers relevant for CeX (e.g., "Hogwarts Legacy PS5", "iPhone 13 Pro Max 256GB Unlocked", "Xbox Series X 1TB Console").
        - Prioritise specific identifiers like Brand, Model, Platform, Storage, and any other attributes that define the specific variant of the product CeX would buy.
        - Use information from the description to clarify or enhance the query if it provides essential product details (e.g., "Steelbook Edition", "unlocked", specific damage that affects CeX valuation).
        - Ignore extra words like "sealed", "disc only", "for", "very good condition", "cracked screen", "fast postage", "uploaded X hours ago", "bought as a present", "used a handful of times", "disk is scratch free" etc., unless they are essential product variations or critical condition notes (e.g., "unlocked" for phones, major damage).
        - If the title/details indicate multiple items (e.g., a bundle of games), try to create a query for the most prominent single item that CeX would likely buy, or the first identifiable main product. If it's too complex or clearly multiple distinct items not sold together by CeX, return 'N/A'.
        - If the item is a generic accessory (like a 'case', 'cable', 'stand', 'controller grip') and not a specific, named product that CeX would buy (like a specific controller or console), return the single word: N/A
        Category: "{category}"
        Vinted Title: "{title}"
        Vinted Description: "{description}"

        Additional Scraped Attributes:
        {attributes_str}

        Clean CeX Query:
        """
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a highly intelligent product normalisation assistant, skilled at creating concise CeX search queries from Vinted product details. Your output must ONLY be the clean search query."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0
        )
        clean_query = response.choices[0].message.content.strip()
        log_messages.append(f"-> AI generated query for '{title}': '{clean_query}'")
        return clean_query
    except Exception as e:
        log_messages.append(f"-> AI query failed for '{title}': {e}")
        return title

def select_best_cex_match(vinted_item_details, cex_results, log_messages):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        log_messages.append("-> ERROR: OPENAI_API_KEY not found. Cannot select best match.")
        return None

    formatted_results = "\n".join([f"{i+1}. Title: {res['title']}, Link: {res['link']}" for i, res in enumerate(cex_results)])
    
    try:
        client = OpenAI(api_key=api_key)
        prompt = f"""
        You are an expert product matcher. A user wants to find the CeX equivalent of a Vinted item.
        Based on the Vinted item details below, choose the best match from the list of CeX search results.

        **Vinted Item Details:**
        - Title: "{vinted_item_details.get('title', 'N/A')}"
        - Description: "{vinted_item_details.get('description', 'N/A')}"
        - Attributes: {vinted_item_details.get('scraped_attributes', {})}

        **CeX Search Results:**
        {formatted_results}

        **Instructions:**
        1. Carefully compare the Vinted item's platform (e.g., PS5, Xbox, PC), edition (e.g., Day One Edition, Standard), and core name to the CeX results.
        2. Select the most accurate match. For example, if the Vinted item is for PS5, do not choose a PC or Xbox version.
        3. If there is a clear and confident match, return ONLY the full URL of that item.
        4. If no result is a clear match, return the single word: N/A
        """
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an expert product matcher. Your task is to find the best match for a Vinted item from a list of CeX search results and return only the URL or 'N/A'."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0
        )
        best_match_url = response.choices[0].message.content.strip()
        
        if best_match_url and best_match_url.startswith('http'):
            log_messages.append(f"-> AI selected best match: {best_match_url}")
            return best_match_url
        else:
            log_messages.append("-> AI determined no suitable match was found in CeX results.")
            return None
    except Exception as e:
        log_messages.append(f"-> AI match selection failed: {e}")
        return None


def get_cex_buy_price(driver, query, vinted_item_details, log_messages):
    if not query or query.upper() == 'N/A':
        return None
    try:
        search_url = f"https://uk.webuy.com/sell/search/?stext={query.replace(' ', '+')}"
        driver.get(search_url)
        try:
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.XPATH, "//a[contains(@href,'/sell/product-detail')]"))
            )
        except TimeoutException:
            log_messages.append("-> CeX: Timed out waiting for search results to load.")
            return None

        results = driver.find_elements(By.XPATH, "//div[contains(@class, 'search-product-card')]//a")
        if not results:
            log_messages.append(f"-> CeX: No search results found for query '{query}'.")
            return None

        cex_results = []
        for result in results[:5]:
            try:
                title = result.get_attribute("title")
                link = result.get_attribute("href")
                if title and link:
                    cex_results.append({"title": title, "link": link})
            except Exception:
                continue

        if not cex_results:
            log_messages.append("-> CeX: Could not parse any search results.")
            return None

        best_match_url = select_best_cex_match(vinted_item_details, cex_results, log_messages)
        if not best_match_url:
            return None

        driver.get(best_match_url)
        try:
            accept_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'accept')]"))
            )
            accept_btn.click()
        except (NoSuchElementException, TimeoutException):
            pass

        try:
            WebDriverWait(driver, 15).until(
                EC.visibility_of_element_located((By.XPATH, "//h1"))
            )
            time.sleep(0.5)
            page_html = driver.page_source
            patterns = [
                r'cash[^£]*£\s*([0-9]+(?:\.[0-9]+)?)',
                r'£\s*([0-9]+(?:\.[0-9]+)?)\s*trade-?in[^£]*cash',
            ]
            match = None
            for pat in patterns:
                m = re.search(pat, page_html, flags=re.IGNORECASE)
                if m:
                    match = m
                    break
            
            if match:
                cash_price = float(match.group(1))
                log_messages.append(f"-> CeX: Found cash price £{cash_price:.2f}.")
                return {"price": cash_price, "link": driver.current_url}
            else:
                log_messages.append("-> CeX: Could not find price in page HTML.")
                log_messages.append("--- DEBUG: Page HTML at Price Failure ---")
                log_messages.append(driver.page_source)
                log_messages.append("--- END DEBUG ---")
                return None
        except TimeoutException:
            log_messages.append("-> CeX: Timed out waiting for trade-in section.")
            return None

    except Exception as e:
        log_messages.append(f"-> CeX: An unexpected error occurred during scraping: {type(e).__name__}")
        return None

def scrape_vinted_item_page(driver):
    scraped_attributes = {}
    description = ""
    
    try:
        details_container = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CLASS_NAME, "details-list")))
        detail_items = details_container.find_elements(By.CSS_SELECTOR, "div.details-list__item")

        for item in detail_items:
            try:
                label = item.find_element(By.CSS_SELECTOR, "div.details-list__item-value > span")
                value = item.find_element(By.CSS_SELECTOR, "div.details-list__item-value:last-child > span")
                scraped_attributes[label.text.strip()] = value.text.strip()
            except NoSuchElementException:
                continue
    except Exception:
        pass

    try:
        description_element = WebDriverWait(driver, 3).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[itemprop='description']")))
        description = description_element.text.strip()
    except Exception:
        pass
    
    return scraped_attributes, description

def scrape_vinted_search_page(driver, query, num_items_to_check=200):
    encoded_query = query.replace(' ', '+')
    search_url = f"https://www.vinted.co.uk/catalog?search_text={encoded_query}&order=price_asc&country_id=1"
    
    driver.get(search_url)
    time.sleep(1)

    try:
        accept_button = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler")))
        accept_button.click()
        time.sleep(1)
    except Exception:
        pass

    item_links = set()
    last_height = driver.execute_script("return document.body.scrollHeight")
    
    while len(item_links) < num_items_to_check:
        item_elements = driver.find_elements(By.CSS_SELECTOR, "div[data-testid='grid-item'] a.new-item-box__overlay")

        for el in item_elements:
            link = el.get_attribute('href')
            if link:
                item_links.add(link)

        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            print("-> Reached the end of the search results.")
            break
        last_height = new_height

    return [{'link': link} for link in list(item_links)[:num_items_to_check]]


def process_item(item, search_category):
    log_messages = [f"Processing link: {item['link']}"]
    thread_driver = None
    try:
        thread_driver = get_driver()
        thread_driver.get(item['link'])
        time.sleep(2)
        
        try:
            thread_driver.find_element(By.CSS_SELECTOR, "div[data-testid='item-status-banner']")
            log_messages.append(f"-> Item is sold, skipping.")
            print("\n".join(log_messages))
            return
        except NoSuchElementException:
            pass

        is_scraped = False
        for attempt in range(2):
            try:
                price_element = WebDriverWait(thread_driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-testid='item-price'] p"))
                )
                
                sidebar_content = thread_driver.find_element(By.CSS_SELECTOR, "div.item-page-sidebar-content")
                
                title = sidebar_content.find_element(By.CSS_SELECTOR, "h1[class*='title']").text.strip()
                price_text = price_element.text

                if not price_text or not any(char.isdigit() for char in price_text):
                    raise ValueError("Price text not found or invalid.")

                price = float(re.sub(r'[^\d.]', '', price_text))
                
                item['title'] = title
                item['price'] = price
                is_scraped = True
                break
            except (TimeoutException, ValueError, NoSuchElementException, StaleElementReferenceException) as e:
                if attempt == 0:
                    log_messages.append(f"!! Could not parse title/price, refreshing and retrying. Error: {type(e).__name__}")
                    time.sleep(1)
                    thread_driver.refresh()
                    time.sleep(3)
                else:
                    log_messages.append(f"!! Failed to parse title/price after retrying. Skipping. Error: {type(e).__name__}")
                    log_messages.append("--- DEBUG: Page source at failure ---")
                    log_messages.append(thread_driver.page_source[:2000])
                    log_messages.append("--- END DEBUG ---")
                    print("\n".join(log_messages))
                    return
        
        if not is_scraped:
            print("\n".join(log_messages))
            return

        scraped_attributes, description = scrape_vinted_item_page(thread_driver)
        item['scraped_attributes'] = scraped_attributes
        item['description'] = description

        postage = 'N/A'
        try:
            postage_selector = (By.CSS_SELECTOR, "h3[data-testid='item-shipping-banner-price']")
            postage_element = WebDriverWait(thread_driver, 3).until(EC.presence_of_element_located(postage_selector))
            postage_text = postage_element.text
            cleaned_postage = re.sub(r'[^\d.]', '', postage_text)
            postage = float(cleaned_postage)
        except Exception:
            pass
        item['postage'] = postage

        clean_query = generate_cex_query_from_vinted_listing(item, search_category, log_messages)
        cex_data = get_cex_buy_price(thread_driver, clean_query, item, log_messages)

        postage_cost = item.get('postage')
        if cex_data and isinstance(postage_cost, (int, float)):
            cex_price = cex_data['price']
            buyer_protection_fee = 1.00 + (item['price'] * 0.05)
            total_vinted_cost = item['price'] + postage_cost + buyer_protection_fee
            pnl = cex_price - total_vinted_cost

            if pnl > 0:
                log_messages.append(f"✅ PROFIT FOUND: £{pnl:.2f} for {item['title']}")
                log_profit_detailed(item, cex_data, pnl, total_vinted_cost, search_category)
            else:
                log_messages.append(f"❌ Loss: £{abs(pnl):.2f} for {item['title']}")
        else:
            log_messages.append(f"-> No deal for {item['title']} (No CeX price or postage info found).")

    except (MaxRetryError, NewConnectionError) as e:
        log_messages.append(f"!! Network connection error: {type(e).__name__}. The driver for this thread may have crashed.")
    except Exception as e:
        log_messages.append(f"!! An unexpected error occurred: {e}")
    finally:
        print("\n".join(log_messages))
