#define CAMERA_MODEL_AI_THINKER
#include "camera_pins.h"
#include "BluetoothSerial.h"
#include <esp32cam.h>


// Bluetooth
BluetoothSerial SerialBT;

// Camera Resolutions
static auto loRes = esp32cam::Resolution::find(320, 240);
static auto midRes = esp32cam::Resolution::find(350, 530);
static auto hiRes = esp32cam::Resolution::find(800, 600);

// Loop Control
bool loopActive = false;

// Function Prototypes
void initBT();
void initCamera();
void captureAndSendBT();
void btCallback(esp_spp_cb_event_t event, esp_spp_cb_param_t *param);
void setResolution(int paramInt);

void setup() {
  Serial.begin(115200);
  Serial.println("\nESP32-CAM Setup Starting...");

  initBT();
  initCamera();

  Serial.println("Setup Complete.");
}

void initBT() {
  if (!SerialBT.begin("tingjian-cam")) {
    Serial.println("Bluetooth initialization failed! Restarting...");
    ESP.restart();
  } else {
    Serial.println("Bluetooth initialized. Device name: tingjian-cam");
    SerialBT.register_callback(btCallback);
  }
}

void initCamera() {
  using namespace esp32cam;
  Config cfg;
  cfg.setPins(pins::AiThinker);
  cfg.setResolution(loRes);  // Default resolution
  cfg.setBufferCount(2);
  cfg.setJpeg(40);

  bool ok = Camera.begin(cfg);
  Serial.println(ok ? "Camera initialized successfully." : "Camera initialization failed!");
}

// Bluetooth Callback for Control Messages
void btCallback(esp_spp_cb_event_t event, esp_spp_cb_param_t *param) {
  if (event == ESP_SPP_SRV_OPEN_EVT) {
    Serial.println("Bluetooth Client Connected.");
  } else if (event == ESP_SPP_DATA_IND_EVT) {
    Serial.printf("ESP_SPP_DATA_IND_EVT len=%d, handle=%d\n\n", param->data_ind.len, param->data_ind.handle);
    String stringRead = String(*param->data_ind.data);
    Serial.printf("ParamString: %d\n", stringRead);

    if (stringRead == "start") {
      loopActive = true;
      SerialBT.println("Loop started.");
    } else if (stringRead == "stop") {
      loopActive = false;
      SerialBT.println("Loop stopped.");
    } else if (stringRead.startsWith("res:")) {
      int resParam = stringRead.substring(4).toInt();
      setResolution(resParam);
    } else {
      SerialBT.println("Invalid command.");
    }
  }
}



// Set Camera Resolution
void setResolution(int paramInt) {
  using namespace esp32cam;
  switch (paramInt) {
    case 0:
      Camera.changeResolution(loRes);
      SerialBT.println("Resolution set to Low (320x240).");
      break;
    case 1:
      Camera.changeResolution(midRes);
      SerialBT.println("Resolution set to Medium (350x530).");
      break;
    case 2:
    default:
      Camera.changeResolution(hiRes);
      SerialBT.println("Resolution set to High (800x600).");
      break;
  }
}

// Capture Image and Send via Bluetooth
void captureAndSendBT() {
  using namespace esp32cam;
  auto frame = capture();
  if (!frame) {
    Serial.println("Capture failed.");
    return;
  }

  Serial.printf("Captured image: %d bytes\n", frame->size());
  SerialBT.write(frame->data(), frame->size());
  SerialBT.flush();
  Serial.println("Image sent via Bluetooth.");
}

void loop() {
  if (loopActive) {
    captureAndSendBT();
    delay(7000);  // Delay for 7 seconds between captures
  }
}