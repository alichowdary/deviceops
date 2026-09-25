#include "mqtt_auth.h"

#include <ArduinoJson.h>
#include <esp_random.h>
#include <mbedtls/md.h>
#include <mbedtls/sha256.h>

#include <cstring>


namespace mqtt_auth {
namespace {

constexpr char HEX_DIGITS[] = "0123456789abcdef";
constexpr char AUTH_PREFIX[] = "deviceops-auth-v1";
constexpr char BROKER_AUTH_CONTEXT[] = "deviceops-broker-auth-v1";


bool isLowercaseHex(const char* value, size_t expectedLength) {
    if (value == nullptr || strlen(value) != expectedLength) {
        return false;
    }

    for (size_t index = 0; index < expectedLength; index++) {
        const char character = value[index];
        if (!(
                (character >= '0' && character <= '9') ||
                (character >= 'a' && character <= 'f')
            )) {
            return false;
        }
    }
    return true;
}


void bytesToHex(const uint8_t* bytes, size_t length, char* output) {
    for (size_t index = 0; index < length; index++) {
        output[index * 2] = HEX_DIGITS[bytes[index] >> 4];
        output[index * 2 + 1] = HEX_DIGITS[bytes[index] & 0x0F];
    }
    output[length * 2] = '\0';
}


const char* directionValue(Direction direction) {
    return direction == Direction::DeviceToServer ? "d2s" : "s2d";
}


bool constantTimeEquals(const char* left, const char* right, size_t length) {
    uint8_t difference = 0;
    for (size_t index = 0; index < length; index++) {
        difference |= static_cast<uint8_t>(left[index] ^ right[index]);
    }
    return difference == 0;
}

}  // namespace


bool deriveSigningKey(
    const char* deviceSecret,
    uint8_t signingKey[SIGNING_KEY_SIZE]
) {
    if (deviceSecret == nullptr || deviceSecret[0] == '\0') {
        return false;
    }

    return mbedtls_sha256_ret(
               reinterpret_cast<const unsigned char*>(deviceSecret),
               strlen(deviceSecret),
               signingKey,
               0
           ) == 0;
}


bool deriveBrokerPassword(
    const uint8_t signingKey[SIGNING_KEY_SIZE],
    char brokerPasswordHex[BROKER_PASSWORD_HEX_SIZE + 1]
) {
    if (signingKey == nullptr || brokerPasswordHex == nullptr) {
        return false;
    }

    const mbedtls_md_info_t* sha256Info =
        mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
    if (sha256Info == nullptr) {
        return false;
    }

    uint8_t brokerPassword[SIGNING_KEY_SIZE];
    const int result = mbedtls_md_hmac(
        sha256Info,
        signingKey,
        SIGNING_KEY_SIZE,
        reinterpret_cast<const unsigned char*>(BROKER_AUTH_CONTEXT),
        sizeof(BROKER_AUTH_CONTEXT) - 1,
        brokerPassword
    );
    if (result != 0) {
        memset(brokerPassword, 0, sizeof(brokerPassword));
        return false;
    }

    bytesToHex(
        brokerPassword,
        sizeof(brokerPassword),
        brokerPasswordHex
    );
    memset(brokerPassword, 0, sizeof(brokerPassword));
    return true;
}


void generateBootSessionId(char sessionId[SESSION_ID_HEX_SIZE + 1]) {
    uint8_t randomBytes[SESSION_ID_HEX_SIZE / 2];
    esp_fill_random(randomBytes, sizeof(randomBytes));
    bytesToHex(randomBytes, sizeof(randomBytes), sessionId);
    memset(randomBytes, 0, sizeof(randomBytes));
}


bool sha256Hex(
    const String& body,
    char digestHex[SIGNATURE_HEX_SIZE + 1]
) {
    uint8_t digest[SIGNING_KEY_SIZE];
    const int result = mbedtls_sha256_ret(
        reinterpret_cast<const unsigned char*>(body.c_str()),
        body.length(),
        digest,
        0
    );
    if (result != 0) {
        memset(digest, 0, sizeof(digest));
        return false;
    }

    bytesToHex(digest, sizeof(digest), digestHex);
    memset(digest, 0, sizeof(digest));
    return true;
}


bool computeSignature(
    const uint8_t signingKey[SIGNING_KEY_SIZE],
    Direction direction,
    const char* topic,
    const char* sessionId,
    const String& body,
    char signatureHex[SIGNATURE_HEX_SIZE + 1]
) {
    if (
        signingKey == nullptr || topic == nullptr || topic[0] == '\0' ||
        !isValidSessionId(sessionId)
    ) {
        return false;
    }

    char bodyDigestHex[SIGNATURE_HEX_SIZE + 1];
    if (!sha256Hex(body, bodyDigestHex)) {
        return false;
    }

    String signingInput;
    signingInput.reserve(
        strlen(AUTH_PREFIX) + strlen(directionValue(direction)) +
        strlen(topic) + strlen(sessionId) + strlen(bodyDigestHex) + 5
    );
    signingInput += AUTH_PREFIX;
    signingInput += '\n';
    signingInput += directionValue(direction);
    signingInput += '\n';
    signingInput += topic;
    signingInput += '\n';
    signingInput += sessionId;
    signingInput += '\n';
    signingInput += bodyDigestHex;

    const mbedtls_md_info_t* sha256Info =
        mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
    if (sha256Info == nullptr) {
        return false;
    }

    uint8_t signature[SIGNING_KEY_SIZE];
    const int result = mbedtls_md_hmac(
        sha256Info,
        signingKey,
        SIGNING_KEY_SIZE,
        reinterpret_cast<const unsigned char*>(signingInput.c_str()),
        signingInput.length(),
        signature
    );
    if (result != 0) {
        memset(signature, 0, sizeof(signature));
        return false;
    }

    bytesToHex(signature, sizeof(signature), signatureHex);
    memset(signature, 0, sizeof(signature));
    return true;
}


bool createEnvelope(
    const String& body,
    const uint8_t signingKey[SIGNING_KEY_SIZE],
    Direction direction,
    const char* topic,
    const char* sessionId,
    String& output
) {
    char signatureHex[SIGNATURE_HEX_SIZE + 1];
    if (!computeSignature(
            signingKey,
            direction,
            topic,
            sessionId,
            body,
            signatureHex
        )) {
        return false;
    }

    JsonDocument document;
    document["auth_version"] = 1;
    document["session_id"] = sessionId;
    document["body"] = body;
    document["signature"] = signatureHex;

    output = "";
    output.reserve(body.length() + 192);
    return serializeJson(document, output) > 0;
}


bool parseEnvelope(const String& payload, Envelope& output) {
    JsonDocument document;
    if (deserializeJson(document, payload)) {
        return false;
    }

    JsonObjectConst object = document.as<JsonObjectConst>();
    if (object.isNull() || object.size() != 4) {
        return false;
    }

    JsonVariantConst authVersion = object["auth_version"];
    JsonVariantConst sessionId = object["session_id"];
    JsonVariantConst body = object["body"];
    JsonVariantConst signature = object["signature"];
    if (
        authVersion.is<bool>() || !authVersion.is<int>() ||
        authVersion.as<int>() != 1 || !sessionId.is<const char*>() ||
        !body.is<const char*>() || !signature.is<const char*>()
    ) {
        return false;
    }

    const char* sessionIdValue = sessionId.as<const char*>();
    const char* signatureValue = signature.as<const char*>();
    if (
        !isValidSessionId(sessionIdValue) ||
        !isLowercaseHex(signatureValue, SIGNATURE_HEX_SIZE)
    ) {
        return false;
    }

    output.sessionId = sessionIdValue;
    output.body = body.as<const char*>();
    output.signature = signatureValue;
    return true;
}


bool verifyEnvelope(
    const Envelope& envelope,
    const uint8_t signingKey[SIGNING_KEY_SIZE],
    Direction direction,
    const char* topic
) {
    if (
        !isValidSessionId(envelope.sessionId.c_str()) ||
        !isLowercaseHex(envelope.signature.c_str(), SIGNATURE_HEX_SIZE)
    ) {
        return false;
    }

    char expectedSignature[SIGNATURE_HEX_SIZE + 1];
    if (!computeSignature(
            signingKey,
            direction,
            topic,
            envelope.sessionId.c_str(),
            envelope.body,
            expectedSignature
        )) {
        return false;
    }

    return constantTimeEquals(
        expectedSignature,
        envelope.signature.c_str(),
        SIGNATURE_HEX_SIZE
    );
}


bool isValidSessionId(const char* value) {
    return isLowercaseHex(value, SESSION_ID_HEX_SIZE);
}


bool runInteroperabilitySelfTest() {
    constexpr char TEST_SECRET[] = "deviceops-test-only-secret";
    constexpr char TEST_SESSION_ID[] =
        "0123456789abcdef0123456789abcdef";
    constexpr char TEST_TOPIC[] =
        "deviceops/v1/devices/test-device/telemetry";
    constexpr char EXPECTED_KEY_HEX[] =
        "d69100dd57af5ccdfb56800af1ca5bfa"
        "04b688994a8cebbfda34765c0f42d35a";
    constexpr char EXPECTED_BODY_DIGEST_HEX[] =
        "532c3453e5647433abfbf93581127aa7"
        "9b85426b5a8e269dbda1822a37802f42";
    constexpr char EXPECTED_SIGNATURE[] =
        "65c72f03a11bb3fb66452ba74ad9ecf1"
        "42e7da2a3c49449cd76f47530207c798";
    constexpr char EXPECTED_BROKER_PASSWORD[] =
        "51e72cba8e5b0c924950ca9a77150d47"
        "24d15886dc078f8bfaa3bc7cb18d19d2";
    const String body = "{\"message\":\"hello-deviceops\"}";

    uint8_t signingKey[SIGNING_KEY_SIZE];
    char signingKeyHex[SIGNATURE_HEX_SIZE + 1];
    char bodyDigestHex[SIGNATURE_HEX_SIZE + 1];
    char signatureHex[SIGNATURE_HEX_SIZE + 1];
    char brokerPasswordHex[BROKER_PASSWORD_HEX_SIZE + 1];

    if (!deriveSigningKey(TEST_SECRET, signingKey)) {
        return false;
    }
    bytesToHex(signingKey, sizeof(signingKey), signingKeyHex);

    const bool success =
        constantTimeEquals(
            signingKeyHex,
            EXPECTED_KEY_HEX,
            SIGNATURE_HEX_SIZE
        ) &&
        sha256Hex(body, bodyDigestHex) &&
        constantTimeEquals(
            bodyDigestHex,
            EXPECTED_BODY_DIGEST_HEX,
            SIGNATURE_HEX_SIZE
        ) &&
        computeSignature(
            signingKey,
            Direction::DeviceToServer,
            TEST_TOPIC,
            TEST_SESSION_ID,
            body,
            signatureHex
        ) &&
        constantTimeEquals(
            signatureHex,
            EXPECTED_SIGNATURE,
            SIGNATURE_HEX_SIZE
        ) &&
        deriveBrokerPassword(signingKey, brokerPasswordHex) &&
        constantTimeEquals(
            brokerPasswordHex,
            EXPECTED_BROKER_PASSWORD,
            BROKER_PASSWORD_HEX_SIZE
        );

    memset(signingKey, 0, sizeof(signingKey));
    return success;
}

}  // namespace mqtt_auth
