export type PostcodeResult = {
  postalCode: string
  apartmentName: string
  roadAddress: string
}

const POSTCODE_SCRIPT_ID = 'kakao-postcode-script'
const POSTCODE_SCRIPT_URL =
  'https://t1.kakaocdn.net/mapjsapi/bundle/postcode/prod/postcode.v2.js'

type PostcodeConstructor = NonNullable<Window['kakao']>['Postcode']
let postcodeScriptPromise: Promise<PostcodeConstructor> | undefined

function getPostcodeConstructor(): PostcodeConstructor | undefined {
  return window.kakao?.Postcode ?? window.daum?.Postcode
}

function reloadPostcodeScript(): Promise<PostcodeConstructor> {
  return new Promise((resolve, reject) => {
    document.getElementById(POSTCODE_SCRIPT_ID)?.remove()

    const script = document.createElement('script')
    script.id = POSTCODE_SCRIPT_ID
    script.src = POSTCODE_SCRIPT_URL
    script.async = true

    script.onload = () => {
      const Postcode = getPostcodeConstructor()
      if (Postcode) {
        resolve(Postcode)
        return
      }
      reject(new Error('주소 검색 서비스를 초기화하지 못했습니다.'))
    }
    script.onerror = () => {
      script.remove()
      reject(new Error('주소 검색 서비스 연결이 차단되었습니다. 잠시 후 다시 시도해 주세요.'))
    }

    document.head.appendChild(script)
  })
}

function loadPostcodeScript(): Promise<PostcodeConstructor> {
  const Postcode = getPostcodeConstructor()
  if (Postcode) {
    return Promise.resolve(Postcode)
  }

  if (!postcodeScriptPromise) {
    postcodeScriptPromise = reloadPostcodeScript().catch((error: unknown) => {
      postcodeScriptPromise = undefined
      throw error
    })
  }

  return postcodeScriptPromise
}

function toPostcodeResult(data: KakaoPostcodeData): PostcodeResult {
  return {
    postalCode: data.zonecode,
    apartmentName: data.buildingName,
    roadAddress: data.roadAddress,
  }
}

export async function openPostcodeSearch(
  onComplete: (result: PostcodeResult) => void,
) {
  const Postcode = await loadPostcodeScript()

  new Postcode({
    oncomplete: (data) => onComplete(toPostcodeResult(data)),
  }).open()
}
