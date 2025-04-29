import uvicorn
from dotenv import load_dotenv, find_dotenv


if __name__ == "__main__":
    load_dotenv(find_dotenv())

    uvicorn.run("server:app", host="0.0.0.0", port=9999, reload=True) 