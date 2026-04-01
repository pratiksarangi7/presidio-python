import asyncio
import random
from playwright.async_api import async_playwright

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
]

async def extract_products_from_page(page, url):
    await page.goto(url)
    await page.wait_for_selector('.RGLWAk') 
    
    products_data = []
    cards = await page.query_selector_all('.RGLWAk')
    
    for card in cards:
        title_el = await card.query_selector('a.pIpigb')
        name = await title_el.get_attribute('title') if title_el else "N/A"
        raw_url = await title_el.get_attribute('href') if title_el else ""
        sku = raw_url.split('?')[0] if raw_url else name
        
        price_el = await card.query_selector('.hZ3P6w')
        price_text = await price_el.inner_text() if price_el else "0"
        current_price = float(price_text.replace('₹', '').replace(',', '').strip())
        
        products_data.append({
            'sku': sku,
            'name': name,
            'price': current_price
        })
        
    return products_data

async def run_scraper():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False) 
        context = await browser.new_context(user_agent=random.choice(USER_AGENTS))
        page = await context.new_page()
        
        all_scraped_data = []
        
        for page_num in range(1, 4):
            url = f"https://www.flipkart.com/search?q=speaker&page={page_num}"
            data = await extract_products_from_page(page, url)
            all_scraped_data.extend(data)
            await asyncio.sleep(random.uniform(1.5, 4.0))
            
        await browser.close()
        return all_scraped_data

