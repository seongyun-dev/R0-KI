// src/types/kakao-postcode.d.ts

export {}

declare global {
  interface KakaoPostcodeData {
    zonecode: string
    roadAddress: string
    buildingName: string
  }

  interface Window {
    kakao?: {
      Postcode: new (options: {
        oncomplete: (data: KakaoPostcodeData) => void
      }) => {
        open: () => void
      }
    }
    daum?: {
      Postcode: new (options: {
        oncomplete: (data: KakaoPostcodeData) => void
      }) => {
        open: () => void
      }
    }
  }
}
