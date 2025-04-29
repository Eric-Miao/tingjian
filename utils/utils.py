import base64

# Helper functions remain largely the same
def base64_encode_image(image):
    with open(image, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')
