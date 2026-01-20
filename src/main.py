# In your main.py or app.py
from fastapi import FastAPI
from routes.movies import router as movies_router

app = FastAPI()

# Include the movies router
app.include_router(movies_router, prefix="/api/v1/theater/movies", tags=["movies"])
