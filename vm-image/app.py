from fastapi import FastAPI
import uvicorn
import socket

app = FastAPI()


@app.get("/")
def read_root():
    hostname = socket.gethostname()
    return {"message": "Hello from AI SRE Demo App", "host": hostname}


@app.get("/health")
def read_health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
