from fastapi import FastAPI

app = FastAPI(title="AI Theater API")


@app.get("/health")
def health():
    return {"status": "ok"}
