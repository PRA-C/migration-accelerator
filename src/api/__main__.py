"""Launch uvicorn for Migration Accelerator API."""

import os

import uvicorn
from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    host = os.getenv("API_HOST", "127.0.0.1")
    port = int(os.getenv("API_PORT", "8000"))
    print(f"API at http://{host}:{port}/api/health")
    print(f"Docs at http://{host}:{port}/docs")
    uvicorn.run(
        "api.main:app",
        host=host,
        port=port,
        reload=os.getenv("API_RELOAD", "true").lower() == "true",
    )


if __name__ == "__main__":
    main()
