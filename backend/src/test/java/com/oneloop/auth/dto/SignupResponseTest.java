package com.oneloop.auth.dto;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class SignupResponseTest {

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Test
    void serializesIsNewApartmentAndAccessToken() {
        JsonNode json = objectMapper.valueToTree(new SignupResponse(false, "access-token"));

        assertThat(json.size()).isEqualTo(2);
        assertThat(json.get("isNewApartment").asBoolean()).isFalse();
        assertThat(json.get("accessToken").asText()).isEqualTo("access-token");
        assertThat(json.has("newApartment")).isFalse();
    }
}
