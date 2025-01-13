import base64
import io
import os
import time
from datetime import datetime, timedelta, UTC
from PIL import Image
from flask import Flask, request, render_template, url_for, redirect, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO
from openai import OpenAI
import logging
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from functools import wraps
import jwt
import uuid

from dotenv import load_dotenv
from langchain_community.chat_models.tongyi import ChatTongyi
from langchain_core.messages import HumanMessage, SystemMessage

# Add these imports (if not already present)
from functools import wraps
from flask import jsonify, request

# Add after other configurations
load_dotenv()
qwen_api_key = os.getenv('DASHSCOPE_API_KEY')
API_TOKENS = set(os.getenv('ALLOWED_API_TOKENS', '').split(','))


# Set up logging to display in the console
logger = logging.getLogger("tingjian")
logger.setLevel(logging.DEBUG)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(logging.Formatter('[%(d)s/%(b)s/%(Y)s %(H)s:%(M)s:%(S)s] - %(name)s - %(levelname)s - %(message)s',
                                            defaults={'d': datetime.now().strftime('%d'),
                                                     'b': datetime.now().strftime('%b'),
                                                     'Y': datetime.now().strftime('%Y'),
                                                     'H': datetime.now().strftime('%H'),
                                                     'M': datetime.now().strftime('%M'),
                                                     'S': datetime.now().strftime('%S')}))
logger.addHandler(console_handler)

# Flask application setup
app = Flask(__name__, static_url_path='/static', static_folder='uploaded_images')
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'your-default-secret-key-for-development')

socketio = SocketIO(app)
CORS(app, resources={r"/*": {"origins": "*"}})

# OpenAI API setup
api_key = os.environ.get("API_KEY", None)
if api_key is None:
    logger.info("Missing API_KEY")
else:
    client = OpenAI(api_key=api_key)

if qwen_api_key is None:
    logger.info("Missing Qwen API KAY")
else:
    client = OpenAI(
    # 若没有配置环境变量，请用百炼API Key将下行替换为：api_key="sk-xxx"
        api_key=qwen_api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    logger.info("Qwen client loaded")

# Add Login Manager setup after Flask app initialization
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Add a simple User class
class User(UserMixin):
    def __init__(self, id):
        self.id = id

# Add user loader
@login_manager.user_loader
def load_user(user_id):
    return User(user_id)

def require_jwt_token(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({"error": "No Authorization header"}), 401
        
        try:
            # Check if header follows "Bearer <token>" format
            auth_type, token = auth_header.split(' ')
            if auth_type.lower() != 'bearer':
                return jsonify({"error": "Invalid authorization type"}), 401
            
            # Verify and decode the JWT token
            try:
                payload = jwt.decode(
                    token, 
                    os.getenv('JWT_SECRET_KEY'), 
                    algorithms=["HS256"]
                )
                
                # Log the expiration time
                logger.info(f"Token expiration time: {datetime.fromtimestamp(payload['exp'])}")
                
                # For regular tokens, let jwt.decode handle expiration
                return f(*args, **kwargs)
                
            except jwt.ExpiredSignatureError:
                return jsonify({"error": "Token has expired"}), 401
            except jwt.InvalidTokenError:
                return jsonify({"error": "Invalid token"}), 401
                
        except ValueError:
            return jsonify({"error": "Invalid Authorization header format"}), 401
            
    return decorated_function

# Add this utility function to generate JWT tokens (you'll need this for your login route)
def generate_jwt_token(user_id=None,immortal=False):
    
    if immortal:
        expiration = datetime.now(UTC) + timedelta(weeks=9999)
    else:
        expiration = datetime.now(UTC) + timedelta(hours=24)  # Token expires in 24 hours

    return jwt.encode(
        {
            'user_id': user_id if user_id is not None else str(uuid.uuid4()),
            'exp': expiration
        },
        os.getenv('JWT_SECRET_KEY', 'your-secret-key'),
        algorithm="HS256"
    )

# Add login routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        # Replace with your actual authentication logic
        if username == os.getenv('ADMIN_USERNAME') and password == os.getenv('ADMIN_PASSWORD'):
            user = User(username)
            login_user(user)
            return redirect(url_for('index'))
        return 'Invalid credentials'
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# Protect your existing routes with @login_required
@app.route("/")
@login_required
def index():
    # Get the latest image and description files
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

    # Get the latest image and description if available
    latest_image = images[0] if images else None
    latest_description = descriptions[0] if descriptions else None

    # Construct file paths for rendering
    latest_image_url = (
        url_for("static", filename=latest_image) if latest_image else None
    )

    logger.debug(f"latest_image_url:{latest_image_url}")
    latest_description_text = (
        open(os.path.join(image_dir, latest_description)).read()
        if latest_description
        else "No description available."
    )

    return render_template(
        "index.html",
        latest_image=latest_image_url,
        latest_description=latest_description_text,
    )

@app.route("/upload", methods=["POST"])
@require_jwt_token
def upload_image():
    logger.info("Image received!")
    image_received_time = time.time()

    # Decode the image from the POST request
    image = Image.open(io.BytesIO(request.get_data()))
    filename = _save_image(image)

    # Generate a description (mocked for now)
    description = 'test ' + str(image_received_time)
    # Uncomment to enable real AI-based descriptions:
    description = _tongyi_get_description_from_image(filename)
    _save_description(description)

    # Emit the description to connected clients
    logger.info(
        f"Emitting new description: {description} (latency: {time.time() - image_received_time:.2f}s)"
    )
    socketio.emit("new_description", {"message": description})

    return "OK", 200


# Helper function to encode images as Base64
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

    prompt = "你需要将图片描述给看不到这个图片的人. 请简略的描述图片内容,包括图片中的物体和拍摄者的相对位置关系. 不要提及这是一张图片. 越短越好"

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


# Main block to run the app
if __name__ == "__main__":
    # Ensure the uploaded_images directory exists
    if not os.path.exists("uploaded_images"):
        logger.info("Creating uploaded_images directory")
        os.makedirs("uploaded_images")

    # Run the Flask application on localhost at port 5000
    socketio.run(app, host="0.0.0.0", port=9999, debug=True)