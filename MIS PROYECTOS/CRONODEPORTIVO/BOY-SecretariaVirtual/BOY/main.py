from fastapi import FastAPI
from routers.whatsapp import router as whatsapp_router

app = FastAPI(title="Chatbot Secretaria - Patinaje")

app.include_router(whatsapp_router)

@app.get("/")
def health_check():
    return {"status": "ok", "mensaje": "Bot de patinaje activo"}


## ajecuar server
##  uvicorn main:app --reload

## ngrok http 8000
