import io
import os
import time
from datetime import datetime, timedelta, UTC
from PIL import Image, ImageOps
from fastapi import FastAPI, Request, Response, HTTPException, status, Depends,Security
from fastapi.security.api_key import APIKeyHeader

from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from functools import wraps
from typing import Optional

import json

from contextlib import asynccontextmanager


from llm_core.llm_core import tingjianLLM
from utils.log_utils import get_logger



logger = get_logger()

llm_client = tingjianLLM()  

# Configuration

LATEST_IMAGE = None
STATIC_IMAGE_DIR = "./uploaded_images/"

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
async def upload_image(request: Request, credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):

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

    description = llm_client.tongyi_get_description_from_image(filename)
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

    params = await request.json()
    logger.info(f"Ask params: {params}")
    
    if LATEST_IMAGE:
        question = params.get("question", "请为了仔细描述周围的环境,包括物体和拍摄者的相对位置关系.")
        description = llm_client.tongyi_get_followup_from_image(LATEST_IMAGE, question)
        
    else:
        description = "请拍摄一张你面前的照片,我可以为你描述周围的环境,你也可以进一步向我进行提问,我将尽我所能帮助你."
        
    logger.info(f"Description: {description}")
    return {"status": "OK",
            "description": description}
        

# Helper function to save images locally
def _save_image(image):
    
    if not os.path.exists(STATIC_IMAGE_DIR):
        os.makedirs(STATIC_IMAGE_DIR)

    datestr = datetime.now().strftime("%Y-%m-%d_%H%M%S.%f")[:-3]
    filename = os.path.join(STATIC_IMAGE_DIR, f"{datestr}.jpg")
    # img_corrected = ImageOps.exif_transpose(image)
    # logger.info('Image orientation corrected')
    # img_corrected.save(fp=filename)
    
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