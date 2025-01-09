#include <WebServer.h>
#include <WiFi.h>
#include <esp32cam.h>
 
const char* WIFI_SSID = "301_home"; 
const char* WIFI_PASS = ".W23P*ZLBApJ";
const char *httpPostServer = "http://<YOUR HTTP SERVER IP:PORT>/upload";

// WebServer server(80);
 
 
// static auto loRes = esp32cam::Resolution::find(320, 240);
// static auto midRes = esp32cam::Resolution::find(350, 530);
// static auto hiRes = esp32cam::Resolution::find(800, 600);
// void serveJpg()
// {
//   auto frame = esp32cam::capture();
//   if (frame == nullptr) {
//     Serial.println("CAPTURE FAIL");
//     server.send(503, "", "");
//     return;
//   }
//   Serial.printf("CAPTURE OK %dx%d %db\n", frame->getWidth(), frame->getHeight(),
//                 static_cast<int>(frame->size()));
 
//   server.setContentLength(frame->size());
//   server.send(200, "image/jpeg");
//   WiFiClient client = server.client();
//   frame->writeTo(client);
// }
 
// void handleJpgLo()
// {
//   if (!esp32cam::Camera.changeResolution(loRes)) {
//     Serial.println("SET-LO-RES FAIL");
//   }
//   serveJpg();
// }
 
// void handleJpgHi()
// {
//   if (!esp32cam::Camera.changeResolution(hiRes)) {
//     Serial.println("SET-HI-RES FAIL");
//   }
//   serveJpg();
// }
 
// void handleJpgMid()
// {
//   if (!esp32cam::Camera.changeResolution(midRes)) {
//     Serial.println("SET-MID-RES FAIL");
//   }
//   serveJpg();
// }
 
 
void  setup(){
  Serial.begin(115200);
  Serial.println();
  {
    using namespace esp32cam;
    Config cfg;
    cfg.setPins(pins::AiThinker);
    cfg.setResolution(hiRes);
    cfg.setBufferCount(2);
    cfg.setJpeg(80);
 
    bool ok = Camera.begin(cfg);
    Serial.println(ok ? "CAMERA OK" : "CAMERA FAIL");
  }
  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
  }
  Serial.println("WiFi connected");
//   Serial.print("http://");
//   Serial.println(WiFi.localIP());
//   Serial.println("  /cam-lo.jpg");
//   Serial.println("  /cam-hi.jpg");
//   Serial.println("  /cam-mid.jpg");
 
//   server.on("/cam-lo.jpg", handleJpgLo);
//   server.on("/cam-hi.jpg", handleJpgHi);
//   server.on("/cam-mid.jpg", handleJpgMid);
 
//   server.begin();
}


void uploadImage(uint8_t *imageData, size_t len) {
    // WiFiClient for HTTP request
    WiFiClient client;
    HTTPClient http;

    http.begin(client, httpPostServer);
    http.addHeader("Content-Type", "image/jpeg");

    int httpResponseCode = http.POST(imageData, len);

    if (httpResponseCode > 0) {
        String response = http.getString();
        Serial.println(httpResponseCode);
        Serial.println(response);
    } else {
        Serial.printf("Error on sending POST: %d\n", httpResponseCode);
    }

    http.end();
}

void loop() {
  Serial.println("Capture image");

  blink();
  camera_fb_t * fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("Camera capture failed");
    return;
  }

  // Upload the image
  Serial.printf("Uploading image: %d bytes\n", fb->len);
  uploadImage(fb->buf, fb->len);

  // Return the frame buffer back to the driver
  esp_camera_fb_return(fb);
  delay(7000);
}