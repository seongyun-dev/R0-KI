package com.oneloop.auth.dto;

import com.oneloop.member.domain.Member;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Schema(description = "현재 로그인한 사용자 정보")
@Getter
@NoArgsConstructor
@AllArgsConstructor
public class CurrentMemberResponse {

    @Schema(description = "사용자 식별자", example = "1")
    private Long memberId;

    @Schema(description = "로그인 아이디", example = "admin")
    private String username;

    @Schema(description = "사용자 이름", example = "관리자")
    private String name;

    @Schema(description = "휴대전화 번호", example = "010-1234-5678")
    private String phoneNumber;

    @Schema(description = "소속 아파트 단지 식별자", example = "1")
    private Long apartmentComplexId;

    @Schema(description = "소속 아파트 단지 이름", example = "원루프 아파트")
    private String apartmentComplexName;

    public static CurrentMemberResponse from(Member member) {
        return new CurrentMemberResponse(
                member.getId(),
                member.getUsername(),
                member.getName(),
                member.getPhoneNumber(),
                member.getApartmentComplex().getId(),
                member.getApartmentComplex().getName());
    }
}
