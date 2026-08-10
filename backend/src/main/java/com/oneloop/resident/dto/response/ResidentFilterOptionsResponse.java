package com.oneloop.resident.dto.response;

import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;
import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
@Schema(description = "입주민 목록 필터 옵션 응답")
public class ResidentFilterOptionsResponse {

    @Schema(description = "단지에 등록된 동 목록", example = "[\"101\", \"102\", \"103\"]")
    private List<String> buildingNumbers;

    public static ResidentFilterOptionsResponse from(List<String> buildingNumbers) {
        return ResidentFilterOptionsResponse.builder().buildingNumbers(buildingNumbers).build();
    }
}
