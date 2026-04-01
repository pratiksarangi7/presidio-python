import sys
from database import Session, Product

sys.stdout.reconfigure(encoding='utf-8')

def simulate_price_drop():
    session = Session()
    
    product = session.query(Product).first()
    
    if product:
        print(f"Product: {product.name}")
        print(f"Old Price: ₹{product.current_price}")
        
        product.current_price -= 50.0 
        
        session.commit()
        print(f"New Price saved: ₹{product.current_price}")
        print("\nSuccess! Now run your scraper (main.py) to see if it catches the change.")
    else:
        print("No products found in the database. Run the scraper first!")

    session.close()

if __name__ == "__main__":
    simulate_price_drop()