#include <WebServer.h>
#include <WiFi.h>
#include <esp32cam.h>
#include <HTTPClient.h>
#include <WiFiManager.h> // https://github.com/tzapu/WiFiManager


const char* WIFI_SSID = ""; 
const char* WIFI_PASS = "";
const char *httpPostServer = "https://project.ericmiao.xyz/tingjian/upload";

WebServer server(80);

static auto loRes = esp32cam::Resolution::find(320, 240);
static auto midRes = esp32cam::Resolution::find(350, 530);
static auto hiRes = esp32cam::Resolution::find(800, 600);

bool loopActive = false; // Flag to control the loop

void handleJpgLo() {
  if (!esp32cam::Camera.changeResolution(loRes)) {
    Serial.println("SET-LO-RES FAIL");
  }
  Serial.println("SET-LO-RES SUCCEED");
  server.send(200, "text/plain", "SET-LO-RES SUCCEED");
}

void handleJpgHi() {
  if (!esp32cam::Camera.changeResolution(hiRes)) {
    Serial.println("SET-HI-RES FAIL");
  }
  Serial.println("SET-HI-RES SUCCEED");
  server.send(200, "text/plain", "SET-HI-RES SUCCEED");
}

void handleJpgMid() {
  if (!esp32cam::Camera.changeResolution(midRes)) {
    Serial.println("SET-MID-RES FAIL");
  }
  Serial.println("SET-MID-RES SUCCEED");
  server.send(200, "text/plain", "SET-MID-RES SUCCEED");
}

void startLoop() {
  loopActive = true;
  Serial.println("Loop started");
  server.send(200, "text/plain", "Loop started");
}

void stopLoop() {
  loopActive = false;
  Serial.println("Loop stoped");
  server.send(200, "text/plain", "Loop stopped");
}



 
 
void WiFisetup() {
    WiFi.mode(WIFI_STA); // explicitly set mode, esp defaults to STA+AP
    // it is a good practice to make sure your code sets wifi mode how you want it.
 
    // put your setup code here, to run once:
    Serial.begin(115200);
    
    //WiFiManager, Local intialization. Once its business is done, there is no need to keep it around
    WiFiManager wm;
 
    // reset settings - wipe stored credentials for testing
    // these are stored by the esp library
    // wm.resetSettings();
 
    // Automatically connect using saved credentials,
    // if connection fails, it starts an access point with the specified name ( "AutoConnectAP"),
    // if empty will auto generate SSID, if password is blank it will be anonymous AP (wm.autoConnect())
    // then goes into a blocking loop awaiting configuration and will return success result
 
    bool res;
    // res = wm.autoConnect(); // auto generated AP name from chipid
    res = wm.autoConnect("AutoConnectAP"); // anonymous ap
    // res = wm.autoConnect("AutoConnectAP","password"); // password protected ap
 
    if(!res) {
        Serial.println("Failed to connect");
        // ESP.restart();
    } 
    else {
        //if you get here you have connected to the WiFi    
        Serial.println("connected...yeey :)");
    }
 
}


void setup() {
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
  // WiFi.begin(WIFI_SSID, WIFI_PASS);
  WiFisetup();
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
  }
  Serial.print("http://");
  Serial.println(WiFi.localIP());
  Serial.println("  /setLow");
  Serial.println("  /setHigh");
  Serial.println("  /setMid");
  Serial.println("  /start");
  Serial.println("  /stop");

  server.on("/setLow", handleJpgLo);
  server.on("/setHigh", handleJpgHi);
  server.on("/setMid", handleJpgMid);
  server.on("/start", startLoop);
  server.on("/stop", stopLoop);
  
  server.begin();
}

void uploadImage(uint8_t *imageData, size_t len) {
    // WiFiClient for HTTP request
    WiFiClient client;
    HTTPClient http;

    String recv_token = "nRD34AjaTPD-JSwd_Tff3VlNyUJmforx2P07jdHpylU"; // Complete Bearer token
    recv_token = "Bearer " + recv_token;	// Adding "Bearer " before token
    http.begin(client, httpPostServer);

    // http.addHeader("Authorization", recv_token); // Adding Bearer token as HTTP header
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
  server.handleClient();

  if (loopActive) {
    // Capture image
    Serial.println("Capturing image for upload...");
    auto frame = esp32cam::capture();
    if (frame == nullptr) {
      Serial.println("CAPTURE FAIL");
      return;
    }
    // Upload the image
    Serial.printf("Uploading image: %d bytes\n", frame->size());
    uploadImage(frame->data(), frame->size()); // Upload the captured image

    // Delay for 7 seconds
    delay(7000);
  }
}