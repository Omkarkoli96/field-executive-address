from sqlalchemy import Column, Integer, String, Float
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class GeocodeCache(Base):
    """Caches address -> (lat, lon) lookups so re-running a comparison, or
    comparing the same address across different uploads, doesn't re-hit the
    geocoding service every time."""
    __tablename__ = "geocode_cache"

    id = Column(Integer, primary_key=True)
    address = Column(String, unique=True, index=True, nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    found = Column(String, default="PENDING")
