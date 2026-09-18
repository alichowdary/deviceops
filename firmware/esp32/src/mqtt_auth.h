#pragma once

#include <Arduino.h>

#include <cstddef>
#include <cstdint>


namespace mqtt_auth {

constexpr size_t SIGNING_KEY_SIZE = 32;
constexpr size_t SESSION_ID_HEX_SIZE = 32;
constexpr size_t SIGNATURE_HEX_SIZE = 64;

enum class Direction : uint8_t {
    DeviceToServer,
    ServerToDevice,
};

struct Envelope {
    String sessionId;
    String body;
    String signature;
};

bool deriveSigningKey(
    const char* deviceSecret,
    uint8_t signingKey[SIGNING_KEY_SIZE]
);

void generateBootSessionId(char sessionId[SESSION_ID_HEX_SIZE + 1]);

bool sha256Hex(
    const String& body,
    char digestHex[SIGNATURE_HEX_SIZE + 1]
);

bool computeSignature(
    const uint8_t signingKey[SIGNING_KEY_SIZE],
    Direction direction,
    const char* topic,
    const char* sessionId,
    const String& body,
    char signatureHex[SIGNATURE_HEX_SIZE + 1]
);

bool createEnvelope(
    const String& body,
    const uint8_t signingKey[SIGNING_KEY_SIZE],
    Direction direction,
    const char* topic,
    const char* sessionId,
    String& output
);

bool parseEnvelope(const String& payload, Envelope& output);

bool verifyEnvelope(
    const Envelope& envelope,
    const uint8_t signingKey[SIGNING_KEY_SIZE],
    Direction direction,
    const char* topic
);

bool isValidSessionId(const char* value);
bool runInteroperabilitySelfTest();

}  // namespace mqtt_auth
