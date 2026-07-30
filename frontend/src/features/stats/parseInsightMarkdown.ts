/**
 * 백엔드 insightContent 마크다운(## 섹션 + - 불릿)을
 * 기존 st-in 카드 레이아웃에 맞게 파싱한다.
 */
export type ParsedInsightSection = {
  title: string
  body: string
}

export function parseInsightMarkdown(content: string): ParsedInsightSection[] {
  return content
    .split(/^##\s+/m)
    .map((block) => block.trim())
    .filter(Boolean)
    .map((block) => {
      const lines = block.split('\n')
      const title = lines[0]?.trim() ?? ''
      const body = lines
        .slice(1)
        .map((line) => line.replace(/^[-*]\s+/, '').trim())
        .filter(Boolean)
        .join('\n')
      return { title, body }
    })
    .filter((section) => section.title && section.body)
}
