import os
import re
import time
import random
from openai import OpenAI
from dotenv import load_dotenv
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    StaleElementReferenceException,
)
from urllib3.exceptions import MaxRetryError, NewConnectionError

from utils import get_driver, log_profit_detailed, print_and_log

def generate_cex_query_from_vinted_listing(vinted_item_details, category, log_messages):
    """
    Uses OpenAI API to generate a clean search query from Vinted item details.
    """
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        log_messages.append("-> ERROR: OPENAI_API_KEY not found. Using item title as fallback.")
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

def get_cex_buy_price(driver, query, log_messages):
    """
    Scrapes the CeX 'webuy' price for a given query with improved stability.
    """
    if not query or query.upper() == 'N/A':
        return None
        
    try:
        search_url = f"https://uk.webuy.com/search/?stext={query.replace(' ', '+')}"
        driver.get(search_url)
        
        try:
            accept_button = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Accept All']")))
            accept_button.click()
            time.sleep(0.5)
        except Exception:
            pass
        
        try:
            if driver.find_element(By.CSS_SELECTOR, "div.cx-no-results").is_displayed():
                log_messages.append(f"-> CeX: No results found for '{query}'.")
                return None
        except NoSuchElementException:
            pass

        first_result_selector = (By.CSS_SELECTOR, "a.product-name")
        first_result = WebDriverWait(driver, 15).until(EC.element_to_be_clickable(first_result_selector))
        
        log_messages.append(f"-> CeX: Clicking first result '{first_result.text.strip()}'")
        
        driver.execute_script("arguments[0].click();", first_result)
        
        price_element_selector = (By.XPATH, "//div[contains(@class, 'sell-cta-row')]//div[strong[normalize-space(text())='CASH']]/span[@class='offer-price']")
        price_element = WebDriverWait(driver, 15).until(EC.visibility_of_element_located(price_element_selector))
        price_text = price_element.text

        if price_text:
            price_cleaned = re.sub(r'[^\d.]', '', price_text)
            cex_product_url = driver.current_url
            log_messages.append(f"-> CeX: Found cash price £{price_cleaned}.")
            return {'price': float(price_cleaned), 'link': cex_product_url}
        
        return None
    except TimeoutException:
        log_messages.append(f"-> CeX: Timed out waiting for search result or price element for query '{query}'.")
        return None
    except Exception as e:
        log_messages.append(f"-> CeX: An unexpected error occurred during scraping for query '{query}': {type(e).__name__} - {e}")
        return None


def scrape_vinted_item_page(driver):
    """
    Scrapes attributes and description from a Vinted item page.
    """
    scraped_attributes = {}
    description = ""
    
    try:
        details_container = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CLASS_NAME, "details-list")))
        detail_items = details_container.find_elements(By.CSS_SELECTOR, "div.details-list__item")

        for item in detail_items:
            for attempt in range(2):
                try:
                    label = item.find_element(By.CSS_SELECTOR, "div.details-list__item-title").text.strip()
                    value = item.find_element(By.CSS_SELECTOR, "div.details-list__item-value").text.strip()
                    scraped_attributes[label] = value
                    break
                except StaleElementReferenceException:
                    if attempt == 1:
                        raise
                    time.sleep(0.5)
                except NoSuchElementException:
                    break
    except Exception:
        pass

    try:
        description_element = WebDriverWait(driver, 3).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[itemprop='description']")))
        description = description_element.text.strip()
    except Exception:
        pass
    
    return scraped_attributes, description

def scrape_vinted_search_page(driver, query, num_items_to_check=200):
    """
    Scrapes item links from Vinted search, handling infinite scroll.
    """
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
            print_and_log("-> Reached the end of the search results.")
            break
        last_height = new_height

    return [{'link': link} for link in list(item_links)[:num_items_to_check]]


def process_item(item, search_category):
    log_messages = [f"Processing link: {item['link']}"]
    thread_driver = None
    try:
        thread_driver = get_driver()
        thread_driver.get(item['link'])
        
        try:
            thread_driver.find_element(By.CSS_SELECTOR, "div[data-testid='item-status-banner']")
            log_messages.append("-> Item is sold, skipping.")
            print_and_log("\n".join(log_messages))
            return
        except NoSuchElementException:
            pass

        is_scraped = False
        for attempt in range(3):
            try:
                sidebar_content = WebDriverWait(thread_driver, 15).until(
                    EC.visibility_of_element_located((By.CSS_SELECTOR, "div.item-page-sidebar-content"))
                )
                
                title = sidebar_content.find_element(By.CSS_SELECTOR, "h1[class*='title']").text.strip()
                price_text = sidebar_content.find_element(By.CSS_SELECTOR, "div[data-testid='item-price'] p").text
                price = float(re.sub(r'[^\d.]', '', price_text))
                
                item['title'] = title
                item['price'] = price
                is_scraped = True
                break
            except (TimeoutException, ValueError, NoSuchElementException, StaleElementReferenceException) as e:
                if attempt < 2:
                    log_messages.append(f"!! Could not parse title/price (Attempt {attempt + 1}), retrying. Error: {type(e).__name__}")
                    time.sleep(random.uniform(1, 2)) # Add random delay
                    thread_driver.refresh()
                else:
                    log_messages.append(f"!! Failed to parse title/price after retries. Skipping. Error: {type(e).__name__}")
                    print_and_log("\n".join(log_messages))
                    return
        
        if not is_scraped:
            print_and_log("\n".join(log_messages))
            return

        scraped_attributes, description = scrape_vinted_item_page(thread_driver)
        item['scraped_attributes'] = scraped_attributes
        item['description'] = description

        postage = 'N/A'
        try:
            postage_selector = (By.CSS_SELECTOR, "h3[data-testid='item-shipping-banner-price']")
            postage_element = WebDriverWait(thread_driver, 5).until(EC.visibility_of_element_located(postage_selector))
            postage_text = postage_element.text
            cleaned_postage = re.sub(r'[^\d.]', '', postage_text)
            postage = float(cleaned_postage)
        except Exception:
            pass
        item['postage'] = postage

        time.sleep(random.uniform(1, 3))
        
        clean_query = generate_cex_query_from_vinted_listing(item, search_category, log_messages)
        cex_data = get_cex_buy_price(thread_driver, clean_query, log_messages)

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
        log_messages.append(f"!! An unexpected error occurred: {e} (Link: {item.get('link', 'N/A')})")
    finally:
        print_and_log("\n".join(log_messages))
