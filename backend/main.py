from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"message": "Software Cup A1 Backend Running"}