package com.oneloop.auth.dto;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class SignupResponseTest {

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Test
    void serializesOnlyIsNewApartment() {
        JsonNode json = objectMapper.valueToTree(new SignupResponse(false));

        assertThat(json.size()).isEqualTo(1);
        assertThat(json.get("isNewApartment").asBoolean()).isFalse();
        assertThat(json.has("newApartment")).isFalse();
    }
}
