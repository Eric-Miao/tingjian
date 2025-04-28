import base64
import io
import os
import time
from datetime import datetime, timedelta, UTC
from PIL import Image
from fastapi import FastAPI, Request, Response, HTTPException, status, Depends,Security
from fastapi.security.api_key import APIKeyHeader

from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
import logging
from functools import wraps
from typing import Optional

import json

from contextlib import asynccontextmanager

from dotenv import load_dotenv

from langchain_community.chat_models.tongyi import ChatTongyi
from langchain_core.messages import HumanMessage, SystemMessage

# Configuration
load_dotenv()

LATEST_IMAGE = None
STATIC_IMAGE_DIR = "./uploaded_images/"

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


# Startup event
@asynccontextmanager
async def lifespan(app: FastAPI):
    if not os.path.exists("uploaded_images"):
        logger.info("Creating uploaded_images directory")
        os.makedirs("uploaded_images")
    logger.info("Startup event completed.")
    yield
    logger.info("Shutdown event completed.")

async def some_authz_func(request: Request):
    try:
        body = await request.body()
        # Store the body content for later use
        request.state.body = body
        # Try to parse as JSON if possible
        try:
            json_data = json.loads(body)
            request.state.json = json_data
            json_str = json.dumps(json_data, indent=2)
        except json.decoder.JSONDecodeError:
            json_str = "Not JSON data"
            request.state.json = None
            
        # Log key request information
        logger.debug(f"Request received: {request.method} {request.url}")
        logger.debug(f"Headers: {dict(request.headers)}")
        logger.debug(f"Query params: {dict(request.query_params)}")
        logger.debug(f"Body content: {body[:200]}..." if len(body) > 200 else f"Body content: {body}")
        logger.debug(f"JSON content: {json_str}")
        
        # Create a new body stream for FastAPI to read again
        async def get_body():
            return request.state.body
            
        request._body = get_body
        
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        
    return None


app = FastAPI(
    lifespan=lifespan,
    # dependencies=[Depends(some_authz_func)]
    )

app.mount("/tingjian/static", StaticFiles(directory="uploaded_images"), name="static")
templates = Jinja2Templates(directory="templates")
# Security
bearer_scheme = HTTPBearer()
PREFIX = '/tingjian'

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

# OpenAI and Qwen client setup
if os.environ.get("API_KEY"):
    client = OpenAI(api_key=os.environ["API_KEY"])
elif os.getenv('DASHSCOPE_API_KEY'):
    client = OpenAI(
        api_key=os.getenv('DASHSCOPE_API_KEY'),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    logger.info("Qwen client loaded")
else:
    logger.info("Missing LLM KEY")
    client = None
    raise ValueError("Missing LLM KEY")


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
    
    global LATEST_IMAGE
    LATEST_IMAGE = filename

    description = _tongyi_get_description_from_image(filename)
    _save_description(description)

    logger.info(
        f"New description: {description} (latency: {time.time() - image_received_time:.2f}s)"
    )
    
    return {"status": "OK",
            "description": description}

@app.post(f"{PREFIX}/ask")
async def ask_image(request: Request, credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    
    if credentials.credentials not in os.getenv("BEARER_TOKENS").split(","):
        logger.warning(f"Unauthorized access attempt with token: {credentials.credentials[:10]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token"
        )    
        
    params = request.query_params
    location = params.get("location", None)
    heading = params.get("heading", None)    
    
    
    if LATEST_IMAGE:
        question = params.get("question", "请为了仔细描述周围的环境,包括物体和拍摄者的相对位置关系.")
        description = _tongyi_get_description_from_image(LATEST_IMAGE, question)
        
    else:
        description = "请拍摄一张你面前的照片,我可以为你描述周围的环境,你也可以进一步向我进行提问,我将尽我所能帮助你."
        
    logger.info(f"Description: {description}")
    return {"status": "OK",
            "description": description}
        

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

def _tongyi_get_description_from_image(image, question="请为我描述周围的环境"):
    logger.info("getting description using tongyi qwen")
    base64_image = _base64_encode_image(image)

    system_prompt = '''
    你是一个导盲助手, 现在一个盲人拍了一张他面前的照片, 你需要将周围的环境. 
    请简略的描述图片内容, 如果用户没有要求详细回复,描述主要物品,忽略一些小物品.
    使用中文的口语的风格进行回复.避免使用列表、加粗等格式
    
    你可以使用以下格式描述物体和位置关系:
    1. "在...的前面"、"在...的后面"、"在...的左边"、"在...的右边"、"在...的上面"、"在...的下面"
    2. "在...的旁边"、"在...的附近"、"在...的周围"、"在...的对面"

    如果有如下物品请注意描述不要忽略:
    1. 交通信号灯, 如 ”现在是红灯“
    2. 人行横道线, 如 ”人行横道线在正前面“
    3. 交通站点建筑, 如 ”公交车站在左边“ “前方是地下通道入口”
    4. 地名/位置 指示牌, 如 ”1号出口在右边“ “这里是地铁10号线的入口”
    5. 盲道, 如 ”盲道在右边“
    
    如果照片中道路被堵塞, 请你描述道路的情况和周围的环境。帮助用户离开堵塞的地方.
    例如: "前面有一辆车挡住了路, 你可以向左转, 继续前行." "前方有一个大坑, 请小心行走." "前面有一个人挡住了路, 请向右转." "前面有一个台阶, 请小心上下." "前方有一个栏杆,请向右转绕开."
    
    '''

    messages = [
            {"role":"system",
             "content": [
                 {
                    "type": "text",
                    "text": system_prompt
                 }
             ]}
            ,{
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}, 
                    },
                    {"type": "text", "text": question},
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
    
    if not os.path.exists(STATIC_IMAGE_DIR):
        os.makedirs(STATIC_IMAGE_DIR)

    datestr = datetime.now().strftime("%Y-%m-%d_%H%M%S.%f")[:-3]
    filename = os.path.join(STATIC_IMAGE_DIR, f"{datestr}.jpg")
    image.save(fp=filename)
    logger.debug(f"Image saved as {filename}")
    return filename

# Helper function to save descriptions locally
def _save_description(description):
    datestr = datetime.now().strftime("%Y-%m-%d_%H%M%S.%f")[:-3]
    filename = os.path.join(STATIC_IMAGE_DIR, f"{datestr}.txt")
    with open(
        file=filename,
        mode="w",
        encoding="utf-8",
    ) as message_file:
        message_file.write(description)
    logger.debug(f"Description saved as {filename}")






# Note: Remove the __main__ block since FastAPI uses uvicorn