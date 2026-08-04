/* S15P11E103-296 미리보기 재빌드 — vite 번들을 HTML 한 파일로 인라인해
   public/ 에 떨군다. public 은 vite 가 변환 없이 그대로 서빙하므로
   인라인 모듈이 html-proxy 로 바뀌어 죽는 문제가 없다. 확인용 임시 스크립트. */
const fs = require('fs')
const path = require('path')
const { execFileSync } = require('child_process')

const here = __dirname
const root = path.resolve(here, '..')

execFileSync('npx', ['vite', 'build', '--config', path.join(here, 'vite.config.ts')], {
  cwd: root,
  stdio: 'inherit',
  shell: true,
})

const dist = path.join(here, 'dist')
let html = fs.readFileSync(path.join(dist, 'index.html'), 'utf8')
const tag = html.match(/<script[^>]*src="([^"]+)"[^>]*><\/script>/)
if (!tag) throw new Error('빌드 결과에서 script 태그를 찾지 못했습니다')

let js = fs.readFileSync(path.join(dist, tag[1].replace(/^\.\//, '')), 'utf8')
// </script> 가 들어 있으면 HTML 파서가 스크립트를 조기 종료한다
js = js.split('</script').join('<\\/script')
// 문자열 replacement 는 $& 같은 치환 패턴을 해석해 미니파이 코드를 망가뜨린다 → 함수 replacer
html = html.replace(tag[0], () => `<script type="module">${js}</script>`)

fs.writeFileSync(path.join(here, 'roki-296-preview.html'), html)
fs.writeFileSync(path.join(root, 'public', 'roki-296-preview.html'), html)
console.log(`inlined ${(html.length / 1024).toFixed(0)}KB → public/roki-296-preview.html`)
