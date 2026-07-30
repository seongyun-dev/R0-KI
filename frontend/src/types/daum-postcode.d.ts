// src/types/kakao-postcode.d.ts

export {}

declare global {
  interface KakaoPostcodeData {
    zonecode: string
    roadAddress: string
    buildingName: string
  }

  interface Window {
    daum?: {
      Postcode: new (options: {
        oncomplete: (data: KakaoPostcodeData) => void
      }) => {
        open: () => void
      }
    }
  }
}