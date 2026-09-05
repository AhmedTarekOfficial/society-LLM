from contextlib import asynccontextmanager
from pathlib import Path
import asyncio

from dotenv import load_dotenv
# Load .env from current dir or project root
load_dotenv()
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from server.routes import tools as tools_routes
from server.routes import agents as agents_routes
from tools.seed import ensure_seeded
from model.agents import run_continuous


# Frontend lives in src/temp (index.html + style.css + app.js)
TEMP_DIR = Path(__file__).parent.parent / "temp"


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_seeded()
    # Start agents loop in background
    # Short idle delay; user messages also wake agents immediately via wake_agents_for_chat.
    task = asyncio.create_task(run_continuous(delay=3.0))
    yield
    task.cancel()


app = FastAPI(title="Society API", version="1.0.0", lifespan=lifespan)

app.include_router(tools_routes.router)
app.include_router(agents_routes.router)


@app.get("/health")
def health():
    return {"status": "ok"}


# Serve the site from the same origin (no CORS needed).
# Router is registered first, so /tools/* and /health keep working.
if TEMP_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(TEMP_DIR), html=True), name="site")
