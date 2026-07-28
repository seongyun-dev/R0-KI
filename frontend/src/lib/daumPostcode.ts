export type PostcodeResult = {
  postalCode: string
  apartmentName: string
  roadAddress: string
}

export function openPostcodeSearch(
  onComplete: (result: PostcodeResult) => void,
) {
  if (!window.daum?.Postcode) {
    throw new Error('주소 검색 서비스를 불러오지 못했습니다.')
  }

  new window.daum.Postcode({
    oncomplete: (data) => {
      onComplete({
        postalCode: data.zonecode,
        apartmentName:data.buildingName,
        roadAddress: data.roadAddress,
      })
    },
  }).open()
}