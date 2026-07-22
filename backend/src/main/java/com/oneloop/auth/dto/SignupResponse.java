package com.oneloop.auth.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.NoArgsConstructor;

@Schema(description = "회원가입 응답")
@NoArgsConstructor
@AllArgsConstructor
public class SignupResponse {

    private boolean isNewApartment;

    @JsonProperty("isNewApartment")
    @Schema(description = "아파트 단지 신규 등록 여부", example = "true")
    public boolean isNewApartment() {
        return isNewApartment;
    }
}
