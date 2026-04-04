import asyncio
import datetime
import yaml

from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

# Load configuration
def load_config():
    with open("config.yml", "r") as f:
        return yaml.safe_load(f)

config = load_config()
DATABASE_URL = config["database"]["url"]

engine = create_async_engine(DATABASE_URL)
AsyncSessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Define the Article model
class Article(Base):
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    url = Column(String, unique=True, index=True)
    source_feed = Column(String)
    published_date = Column(DateTime)
    processed_date = Column(DateTime, default=datetime.datetime.utcnow)
    markdown_path = Column(String)

    def __repr__(self):
        return f"<Article(title='{self.title[:30]}...', url='{self.url}')>"

# Function to create the database tables
async def create_db_and_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

if __name__ == "__main__":
    print("Creating database and tables...")
    asyncio.run(create_db_and_tables())
    print("Done.")