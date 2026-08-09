package com.oneloop.resident.util;

/** 목록 화면처럼 여러 세대의 연락처가 한 번에 노출되는 곳에서는 가운데 자리를 가린다. 전체 번호는 입주민 상세에서만 보여준다. */
public final class PhoneNumberMasker {

    private PhoneNumberMasker() {}

    /**
     * 연락처의 가운데 부분을 *로 가린다. 하이픈이 있는 3-4-4 형태면 가운데 그룹을, 그렇지 않으면 마지막 4자리를 제외한 뒷부분을 가린다.
     *
     * @param phoneNumber 원본 연락처 (null 이면 null 반환)
     * @return 마스킹된 연락처
     */
    public static String mask(String phoneNumber) {
        if (phoneNumber == null || phoneNumber.isBlank()) {
            return phoneNumber;
        }

        String[] parts = phoneNumber.split("-");
        if (parts.length == 3) {
            return parts[0] + "-" + "*".repeat(parts[1].length()) + "-" + parts[2];
        }

        // 하이픈이 없거나 형태가 다르면 뒤 4자리만 남긴다
        if (phoneNumber.length() <= 4) {
            return "*".repeat(phoneNumber.length());
        }
        int visibleFrom = phoneNumber.length() - 4;
        return "*".repeat(visibleFrom) + phoneNumber.substring(visibleFrom);
    }
}
