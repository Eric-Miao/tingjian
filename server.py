import base64
import io
import os
import time
from datetime import datetime, timedelta, UTC
from PIL import Image
from fastapi import FastAPI, Request, Response, HTTPException, status, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
import logging
from functools import wraps
import jwt
import uuid
from typing import Optional

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from langchain_community.chat_models.tongyi import ChatTongyi
from langchain_core.messages import HumanMessage, SystemMessage



# Startup event
# @app.on_event("startup")
@asynccontextmanager
async def lifespan():
    if not os.path.exists("uploaded_images"):
        logger.info("Creating uploaded_images directory")
        os.makedirs("uploaded_images")
    logger.info("Startup event completed.")
    yield
    logger.info("Shutdown event completed.")
   

# Logging setup
logger = logging.getLogger("tingjian")
logger.setLevel(logging.DEBUG)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(logging.Formatter(
    '[%(d)s/%(b)s/%(Y)s %(H)s:%(M)s:%(S)s] - %(name)s - %(levelname)s - %(message)s',
    defaults={'d': datetime.now().strftime('%d'),
              'b': datetime.now().strftime('%b'),
              'Y': datetime.now().strftime('%Y'),
              'H': datetime.now().strftime('%H'),
              'M': datetime.now().strftime('%M'),
              'S': datetime.now().strftime('%S')}))
logger.addHandler(console_handler)


# Configuration
load_dotenv()
qwen_api_key = os.getenv('DASHSCOPE_API_KEY')

# FastAPI application setup
app = FastAPI(lifespan=lifespan)
app.mount("/tingjian/static", StaticFiles(directory="uploaded_images"), name="static")
templates = Jinja2Templates(directory="templates")

PREFIX = '/tingjian'

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

# Security
bearer_scheme = HTTPBearer()

# OpenAI and Qwen client setup
if os.environ.get("API_KEY"):
    client = OpenAI(api_key=os.environ["API_KEY"])
else:
    logger.info("Missing API_KEY")

if qwen_api_key:
    client = OpenAI(
        api_key=qwen_api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    logger.info("Qwen client loaded")
else:
    logger.info("Missing Qwen API KEY")

# Routes
@app.get(f"{PREFIX}/", response_class=HTMLResponse)
async def index(request: Request):
    image_dir = "./uploaded_images/"
    images = sorted(
        [f for f in os.listdir(image_dir) if f.endswith(".jpg")],
        key=lambda x: os.path.getmtime(os.path.join(image_dir, x)),
        reverse=True,
    )
    descriptions = sorted(
        [f for f in os.listdir(image_dir) if f.endswith(".txt")],
        key=lambda x: os.path.getmtime(os.path.join(image_dir, x)),
        reverse=True,
    )

    latest_image = images[0] if images else None
    latest_description = descriptions[0] if descriptions else None

    # latest_image_url = f"/static/{latest_image}" if latest_image else None
    latest_image_url = app.url_path_for("static", path=latest_image) if latest_image else None
    latest_description_text = (
        open(os.path.join(image_dir, latest_description)).read()
        if latest_description
        else "No description available."
    )

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "latest_image": latest_image_url,
            "latest_description": latest_description_text,
        }
    )

@app.post(f"{PREFIX}/upload")
async def upload_image(request: Request,credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):

    if credentials.credentials not in os.getenv("BEARER_TOKENS").split(","):
        logger.warning(f"Unauthorized access attempt with token: {credentials.credentials[:10]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token"
        )    
    
    logger.info("Image received!")
    image_received_time = time.time()

    # Read raw body data
    body = await request.body()
    image = Image.open(io.BytesIO(body))
    filename = _save_image(image)

    description = _tongyi_get_description_from_image(filename)
    _save_description(description)

    logger.info(
        f"New description: {description} (latency: {time.time() - image_received_time:.2f}s)"
    )
    
    return {"status": "OK",
            "description":description}

# Helper functions remain largely the same
def _base64_encode_image(image):
    with open(image, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


# Helper function to generate descriptions using OpenAI
def _get_description_from_image(image):
    base64_image = _base64_encode_image(image)

    prompt = "Give a short description of the image and where objects are located in the image. Do not mention that this is an image. Do not mention weather or geographical location. Less text is better."

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                    },
                ],
            }
        ],
    )
    logger.debug(f"Response: {response}")
    logger.info(f"Response content: {response.choices[0].message.content}")
    return response.choices[0].message.content

def _tongyi_get_description_from_image(image):
    logger.info("getting description using tongyi qwen")
    base64_image = _base64_encode_image(image)

    prompt = "你需要将图片描述给看不到这个图片的人. 请简略的描述图片内容,包括图片中的物体和拍摄者的相对位置关系. 不要提及这是一张图片. 越短越好,是用中文进行回复"

    messages = [
            {"role":"system",
             "content": [
                 {
                    "type": "text",
                    "text": prompt 
                 }
             ]}
            ,{
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}, 
                    },
                    {"type": "text", "text": "这是什么?"},
                ],
            }
        ]

    response = client.chat.completions.create(
        model="qwen-vl-max-latest",
        messages=messages,
    )
    
    logger.debug(f"Response: {response}")
    logger.info(f"Response content: {response.choices[0].message.content}")
    return response.choices[0].message.content

# Helper function to save images locally
def _save_image(image):
    static_image_dir = "./uploaded_images/"
    if not os.path.exists(static_image_dir):
        os.makedirs(static_image_dir)

    datestr = datetime.now().strftime("%Y-%m-%d_%H%M%S.%f")[:-3]
    filename = os.path.join(static_image_dir, f"{datestr}.jpg")
    image.save(fp=filename)
    logger.debug(f"Image saved as {filename}")
    return filename

# Helper function to save descriptions locally
def _save_description(description):
    datestr = datetime.now().strftime("%Y-%m-%d_%H%M%S.%f")[:-3]
    filename = f"./uploaded_images/{datestr}.txt"
    with open(
        file=filename,
        mode="w",
        encoding="utf-8",
    ) as message_file:
        message_file.write(description)
    logger.debug(f"Description saved as {filename}")



# Note: Remove the __main__ block since FastAPI uses uvicorn