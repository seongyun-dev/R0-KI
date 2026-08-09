import { createElement } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import html2canvas from 'html2canvas'
import { jsPDF } from 'jspdf'
import {
  StatsPdfDocument,
  type StatsPdfDocumentProps,
  type StatsPdfInsight,
} from './StatsPdfDocument'
import type {
  DailyEventStat,
  HandlingStat,
  HourlyEventStat,
  StatSummary,
  ZoneShareStat,
} from '../../types/domain'

export type { StatsPdfInsight }

const THEME_VARS = [
  '--graphic',
  '--graphic-soft',
  '--page',
  '--text-1',
  '--text-2',
  '--text-3',
  '--hair',
  '--edge',
  '--track',
  '--focus-in',
  '--sans',
  '--mono',
  '--urgent',
  '--accent-ink',
  '--st-patrol',
  '--st-charge',
  '--st-idle',
] as const

export type ExportStatsPdfOptions = {
  periodLabel: string
  periodKey?: string
  trendTitle: string
  trendPrevLabel: string
  summary: StatSummary
  daily: DailyEventStat[]
  hourly: HourlyEventStat[]
  zones: ZoneShareStat[]
  handling: HandlingStat[]
  insight?: StatsPdfInsight
  /** 테마 CSS 변수 복사 원본 (.r0ki) */
  themeRoot?: HTMLElement | null
  fileName?: string
}

function sleep(ms: number) {
  return new Promise<void>((resolve) => {
    window.setTimeout(resolve, ms)
  })
}

async function waitForLayout() {
  await document.fonts.ready.catch(() => undefined)
  await new Promise<void>((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
  })
  await sleep(320)
}

function applyThemeVars(source: HTMLElement, target: HTMLElement) {
  const cs = getComputedStyle(source)
  for (const name of THEME_VARS) {
    const value = cs.getPropertyValue(name).trim()
    if (value) target.style.setProperty(name, value)
  }
  target.style.color = cs.getPropertyValue('--text-1').trim() || '#142033'
  target.style.background = '#ffffff'
}

function bakeSvgPaints(root: HTMLElement) {
  root.querySelectorAll('svg *').forEach((node) => {
    if (!(node instanceof Element)) return
    const cs = getComputedStyle(node)
    if (cs.fill && cs.fill !== 'none') node.setAttribute('fill', cs.fill)
    if (cs.stroke && cs.stroke !== 'none') node.setAttribute('stroke', cs.stroke)
    if (cs.fillOpacity && cs.fillOpacity !== '1') {
      node.setAttribute('fill-opacity', cs.fillOpacity)
    }
    if (cs.strokeOpacity && cs.strokeOpacity !== '1') {
      node.setAttribute('stroke-opacity', cs.strokeOpacity)
    }
  })
}

function mountPdfDocument(
  themeRoot: HTMLElement,
  props: StatsPdfDocumentProps,
): { host: HTMLElement; root: Root } {
  const host = document.createElement('div')
  host.setAttribute('data-stats-pdf-host', 'true')
  host.style.cssText = [
    'position:fixed',
    'left:-14000px',
    'top:0',
    'width:794px',
    'z-index:-1',
    'pointer-events:none',
    'overflow:visible',
  ].join(';')
  applyThemeVars(themeRoot, host)
  themeRoot.appendChild(host)

  const root = createRoot(host)
  root.render(createElement(StatsPdfDocument, props))
  return { host, root }
}

async function captureSection(el: HTMLElement) {
  bakeSvgPaints(el)
  const width = Math.ceil(el.scrollWidth || el.clientWidth || 794)
  const height = Math.ceil(Math.max(el.scrollHeight, el.clientHeight, 1)) + 4

  return html2canvas(el, {
    backgroundColor: '#ffffff',
    scale: 2,
    useCORS: true,
    logging: false,
    width,
    height,
    windowWidth: width,
    windowHeight: height,
    scrollX: 0,
    scrollY: 0,
  })
}

/**
 * 섹션(카드) 단위 배치.
 * 안 들어가면 새 페이지 — 요소 중간 슬라이스 없음.
 */
function packSections(pdf: jsPDF, canvases: HTMLCanvasElement[]) {
  const pageW = pdf.internal.pageSize.getWidth()
  const pageH = pdf.internal.pageSize.getHeight()
  const margin = 12
  const contentW = pageW - margin * 2
  const maxH = pageH - margin * 2
  let cursorY = margin
  let pageStarted = false

  for (const canvas of canvases) {
    let drawW = contentW
    let drawH = (canvas.height * contentW) / canvas.width

    if (drawH > maxH) {
      const scale = maxH / drawH
      drawH = maxH
      drawW = contentW * scale
    }

    if (!pageStarted) {
      pageStarted = true
      cursorY = margin
    } else if (cursorY + drawH > pageH - margin) {
      pdf.addPage()
      cursorY = margin
    }

    pdf.addImage(canvas.toDataURL('image/png'), 'PNG', margin, cursorY, drawW, drawH)
    cursorY += drawH + 6
  }
}

/**
 * PDF 전용 React 문서 마운트 → .pdf-section 단위 캡처 → 패킹.
 */
export async function exportStatsPdf(options: ExportStatsPdfOptions) {
  const themeRoot =
    options.themeRoot ??
    document.querySelector<HTMLElement>('.r0ki') ??
    document.body

  const overlay = document.createElement('div')
  overlay.style.cssText = [
    'position:fixed',
    'inset:0',
    'z-index:2147483646',
    'background:rgba(252,253,255,.94)',
    'display:flex',
    'align-items:center',
    'justify-content:center',
    'font-family:"Pretendard","Noto Sans KR","Malgun Gothic",sans-serif',
    'font-size:15px',
    'font-weight:600',
    'color:#142033',
  ].join(';')
  overlay.textContent = 'PDF를 생성하는 중입니다…'
  document.body.appendChild(overlay)

  const { host, root } = mountPdfDocument(themeRoot, {
    periodLabel: options.periodLabel,
    periodKey: options.periodKey,
    trendTitle: options.trendTitle,
    trendPrevLabel: options.trendPrevLabel,
    summary: options.summary,
    daily: options.daily,
    hourly: options.hourly,
    zones: options.zones,
    handling: options.handling,
    insight: options.insight,
  })

  try {
    await waitForLayout()

    const sections = Array.from(host.querySelectorAll<HTMLElement>('.pdf-section'))
    if (sections.length === 0) throw new Error('PDF 섹션을 찾지 못했습니다')

    const canvases: HTMLCanvasElement[] = []
    for (const section of sections) {
      canvases.push(await captureSection(section))
    }

    const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' })
    packSections(pdf, canvases)

    const name =
      options.fileName ??
      `patrol-stats-${options.periodKey ?? options.periodLabel.replace(/\s+/g, '-')}.pdf`
    pdf.save(name)
  } finally {
    root.unmount()
    host.remove()
    overlay.remove()
  }
}
