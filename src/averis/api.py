from fastapi import FastAPI

app = FastAPI(title="Averis Shipping Verification", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok", "stage": "foundation", "pipeline_ready": False}
