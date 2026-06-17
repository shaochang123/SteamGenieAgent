const MOBILE_MAX_WIDTH = 767
const TOUCH_TABLET_MAX_WIDTH = 1366
const COARSE_POINTER_QUERY = '(pointer: coarse)'

function browserWindow() {
  return typeof window === 'undefined' ? null : window
}

function viewportSize(win) {
  const doc = win.document?.documentElement
  return {
    width: win.innerWidth || doc?.clientWidth || 0,
    height: win.innerHeight || doc?.clientHeight || 0,
  }
}

function hasCoarsePointer(win) {
  return typeof win.matchMedia === 'function' &&
    win.matchMedia(COARSE_POINTER_QUERY).matches
}

function hasTouchInput(win, coarsePointer) {
  const nav = win.navigator || {}
  return Boolean(coarsePointer || nav.maxTouchPoints > 0 || 'ontouchstart' in win)
}

function updateAppHeight(win, height) {
  win.document?.documentElement?.style.setProperty('--app-height', `${height}px`)
}

export function detectDeviceMode() {
  const win = browserWindow()
  if (!win) {
    return { mode: 'desktop', isTouch: false, width: 0, height: 0 }
  }

  const { width, height } = viewportSize(win)
  const coarsePointer = hasCoarsePointer(win)
  const isTouch = hasTouchInput(win, coarsePointer)
  let mode = 'desktop'
  if (width <= MOBILE_MAX_WIDTH) {
    mode = 'mobile'
  } else if (width <= TOUCH_TABLET_MAX_WIDTH && isTouch) {
    mode = 'tablet'
  }

  updateAppHeight(win, height)
  return { mode, isTouch, width, height }
}

export function watchDeviceMode(callback) {
  const win = browserWindow()
  if (!win) {
    callback(detectDeviceMode())
    return () => {}
  }

  const emit = () => callback(detectDeviceMode())
  const pointerQuery = typeof win.matchMedia === 'function'
    ? win.matchMedia(COARSE_POINTER_QUERY)
    : null

  emit()
  win.addEventListener('resize', emit, { passive: true })
  win.addEventListener('orientationchange', emit, { passive: true })

  if (pointerQuery?.addEventListener) {
    pointerQuery.addEventListener('change', emit)
  } else if (pointerQuery?.addListener) {
    pointerQuery.addListener(emit)
  }

  return () => {
    win.removeEventListener('resize', emit)
    win.removeEventListener('orientationchange', emit)

    if (pointerQuery?.removeEventListener) {
      pointerQuery.removeEventListener('change', emit)
    } else if (pointerQuery?.removeListener) {
      pointerQuery.removeListener(emit)
    }
  }
}
