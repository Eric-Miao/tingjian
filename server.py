import base64
import io
import os
import time
from datetime import datetime
from PIL import Image
from flask import Flask, request, render_template, url_for
from flask_cors import CORS
from flask_socketio import SocketIO
from openai import OpenAI
import logging

# Set up logging
logger = logging.getLogger("tingjian")
logger.setLevel(logging.DEBUG)

# Flask application setup
app = Flask(__name__, static_url_path='/static')

socketio = SocketIO(app)
CORS(app, resources={r"/*": {"origins": "*"}})

# OpenAI API setup
api_key = os.environ.get("API_KEY", None)
if api_key is None:
    logger.info("Missing API_KEY")
else:
    client = OpenAI(api_key=api_key)


@app.route("/")
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
        f"/uploaded_images/{latest_image}" if latest_image else None
    )
    print(f"latest_image_url:{latest_image_url}")
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

# Route for image upload
@app.route("/upload", methods=["POST"])
def upload_image():
    logger.info("Image received!")
    image_received_time = time.time()

    # Decode the image from the POST request
    image = Image.open(io.BytesIO(request.get_data()))
    _save_image(image)

    # Generate a description (mocked for now)
    description = 'test ' + str(image_received_time)
    # Uncomment to enable real AI-based descriptions:
    # description = _get_description_from_image(image)
    _save_description(description)

    # Emit the description to connected clients
    logger.info(
        f"Emitting new description: {description} (latency: {time.time() - image_received_time:.2f}s)"
    )
    socketio.emit("new_description", {"message": description})

    return "OK", 200


# Helper function to encode images as Base64
def _base64_encode_image(image):
    img_buffer = io.BytesIO()
    image.save(img_buffer, format="JPEG")
    byte_data = img_buffer.getvalue()
    return base64.b64encode(byte_data).decode("utf-8")


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


# Helper function to save images locally
def _save_image(image):
    static_image_dir = "./uploaded_images/"
    if not os.path.exists(static_image_dir):
        os.makedirs(static_image_dir)

    datestr = datetime.now().strftime("%Y-%m-%d_%H%M%S.%f")[:-3]
    filename = os.path.join(static_image_dir, f"{datestr}.jpg")
    image.save(fp=filename)
    logger.debug(f"Image saved as {filename}")


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