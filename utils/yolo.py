from ultralytics import YOLO
import cv2
import numpy as np

# Load YOLO model
model = YOLO("yolov10b.pt")

# Read image
# img_path = "/Users/eric/Downloads/2025-05-21_102517.302.jpg"
img_path = "/Users/eric/Downloads/uploaded_images/2025-05-24_173321.988.jpg"
image = cv2.imread(img_path)

# Run inference
results = model(img_path)

# Get masks (if available) or bounding boxes
if hasattr(results[0], 'masks') and results[0].masks is not None:
    mask = np.zeros_like(image, dtype=np.uint8)
    for m in results[0].masks.data:
        m = m.cpu().numpy().astype(np.uint8) * 255
        colored_mask = np.zeros_like(image, dtype=np.uint8)
        color = (0, 255, 0)  # Green mask
        for c in range(3):
            colored_mask[:, :, c] = m * color[c] // 255
        mask = cv2.add(mask, colored_mask)
    # Blend mask with image
    blended = cv2.addWeighted(image, 0.7, mask, 0.3, 0)
else:
    # If no masks, draw bounding boxes as semi-transparent rectangles
    blended = image.copy()
    for box in results[0].boxes.xyxy.cpu().numpy():
        x1, y1, x2, y2 = map(int, box)
        overlay = blended.copy()
        cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 255, 0), -1)
        blended = cv2.addWeighted(overlay, 0.3, blended, 0.7, 0)
        
names = model.names

for r in results:
    for c in r.boxes.cls:
        print(names[int(c)])
    
# Save result
cv2.imwrite("/Users/eric/Downloads/yolo_masked.jpg", blended)