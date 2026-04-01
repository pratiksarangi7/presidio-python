from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime

Base = declarative_base()

class Product(Base):
    __tablename__ = 'products'
    
    id = Column(Integer, primary_key=True)
    sku = Column(String, unique=True, nullable=False) # Using product URL as SKU
    name = Column(String, nullable=False)
    current_price = Column(Float)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

engine = create_engine('sqlite:///ecommerce.db')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)