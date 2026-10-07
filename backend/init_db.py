from app.core.database import Base, engine
from app.models import *
Base.metadata.create_all(bind=engine)
print("DB tables created OK")
