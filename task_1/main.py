import asyncio
import pandas as pd
import schedule
import time
from datetime import datetime
from database import Session, Product
from scraper import run_scraper
import sys

sys.stdout.reconfigure(encoding='utf-8')


def process_data_and_report(scraped_data):
    session = Session()
    price_changes = []
    
    for item in scraped_data:
        db_product = session.query(Product).filter_by(sku=item['sku']).first()
        
        if db_product:
            if db_product.current_price != item['price']:
                change_pct = ((item['price'] - db_product.current_price) / db_product.current_price) * 100
                price_changes.append({
                    'Product': item['name'],
                    'Old Price': f"₹{db_product.current_price:.2f}",
                    'New Price': f"₹{item['price']:.2f}",
                    'Change': f"{change_pct:+.1f}%"
                })
                db_product.current_price = item['price']
        else:
            new_prod = Product(sku=item['sku'], name=item['name'], current_price=item['price'])
            session.add(new_prod)
            
    session.commit()
    session.close()
    
    if price_changes:
        df = pd.DataFrame(price_changes)
        timestamp = datetime.now().strftime("%Y-%m-%d")
        filename = f"price_change_report_{timestamp}.csv"
        df.to_csv(filename, index=False)
        
        print("\n=== Price Change Report ===")
        print(df.to_markdown(index=False))
        print(f"\n{len(price_changes)} price changes detected. Report saved to {filename}")
    else:
        print(f"[{datetime.now()}] No price changes detected today.")

def nightly_job():
    print(f"[{datetime.now()}] Starting nightly scraper job...")
    scraped_data = asyncio.run(run_scraper())
    print(f"[{datetime.now()}] Total: {len(scraped_data)} products scraped. Processing database...")
    process_data_and_report(scraped_data)

if __name__ == "__main__":
    nightly_job()
    
    schedule.every().day.at("02:00").do(nightly_job)
    
    print("Scheduler running. Waiting for next execution window...")
    while True:
        schedule.run_pending()
        time.sleep(60)