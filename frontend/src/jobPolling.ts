type Timer = ReturnType<typeof setTimeout>
interface Scheduler {
  setTimeout: (callback: () => Promise<void>, delay: number) => Timer
  clearTimeout: (timer: Timer) => void
}

/** Retry the complete result-loading step before considering a job finished. */
export function createJobPoller(
  check: (isCurrent: () => boolean) => Promise<boolean>,
  onError: (error: unknown) => void,
  scheduler: Scheduler = { setTimeout, clearTimeout },
) {
  let timer: Timer | undefined
  let generation = 0

  function stop() {
    generation += 1
    if (timer !== undefined) scheduler.clearTimeout(timer)
    timer = undefined
  }

  async function tick(current: number) {
    const isCurrent = () => generation === current
    if (!isCurrent()) return
    timer = undefined
    try {
      if (await check(isCurrent)) {
        if (isCurrent()) stop()
        return
      }
    } catch (error) {
      if (isCurrent()) onError(error)
    }
    if (isCurrent()) timer = scheduler.setTimeout(() => tick(current), 500)
  }

  return {
    start() {
      stop()
      const current = generation
      timer = scheduler.setTimeout(() => tick(current), 500)
    },
    stop,
  }
}
