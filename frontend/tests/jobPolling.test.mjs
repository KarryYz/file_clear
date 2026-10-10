import { strict as assert } from 'node:assert'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import ts from 'typescript'

const source = await readFile(new URL('../src/jobPolling.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
}).outputText
const { createJobPoller } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)

function clock() {
  const callbacks = new Map()
  let next = 0
  return {
    setTimeout(callback) { callbacks.set(++next, callback); return next },
    clearTimeout(timer) { callbacks.delete(timer) },
    get pending() { return callbacks.size },
    async tick() {
      const [timer, callback] = callbacks.entries().next().value
      callbacks.delete(timer)
      await callback()
    },
  }
}

for (const failedRequest of ['details', 'history']) {
  test(`completed job retries a failed ${failedRequest} request before stopping`, async () => {
    const scheduler = clock()
    const requests = []
    const errors = []
    let attempts = 0
    let applied = false
    const poller = createJobPoller(async () => {
      attempts += 1
      requests.push('progress:completed')
      requests.push('details')
      if (failedRequest === 'details' && attempts === 1) throw new Error('disconnected')
      requests.push('history')
      if (failedRequest === 'history' && attempts === 1) throw new Error('disconnected')
      applied = true
      return true
    }, error => errors.push(error.message), scheduler)
    poller.start()
    await scheduler.tick()
    assert.equal(applied, false)
    assert.equal(scheduler.pending, 1)
    await scheduler.tick()
    assert.equal(attempts, 2)
    assert.equal(applied, true)
    assert.equal(scheduler.pending, 0)
    assert.deepEqual(errors, ['disconnected'])
    assert.equal(requests.filter(value => value === 'progress:completed').length, 2)
  })
}

test('requests do not overlap while a previous request is pending', async () => {
  const scheduler = clock()
  let release
  let calls = 0
  const poller = createJobPoller(async () => {
    calls += 1
    await new Promise(resolve => { release = resolve })
    return false
  }, assert.fail, scheduler)
  poller.start()
  const pending = scheduler.tick()
  assert.equal(calls, 1)
  assert.equal(scheduler.pending, 0)
  release()
  await pending
  assert.equal(scheduler.pending, 1)
  poller.stop()
  assert.equal(scheduler.pending, 0)
})

test('unmount invalidates an in-flight request and suppresses stale errors', async () => {
  const scheduler = clock()
  let reject
  let current
  const errors = []
  const poller = createJobPoller(async isCurrent => {
    current = isCurrent
    await new Promise((_, fail) => { reject = fail })
    return true
  }, error => errors.push(error), scheduler)
  poller.start()
  const pending = scheduler.tick()
  poller.stop()
  assert.equal(current(), false)
  reject(new Error('late error'))
  await pending
  assert.deepEqual(errors, [])
  assert.equal(scheduler.pending, 0)
})

test('restarting tracking invalidates the old request without stopping the new job', async () => {
  const scheduler = clock()
  let release
  let oldCurrent
  let calls = 0
  const poller = createJobPoller(async isCurrent => {
    calls += 1
    if (calls === 1) {
      oldCurrent = isCurrent
      await new Promise(resolve => { release = resolve })
    }
    return calls === 1
  }, assert.fail, scheduler)
  poller.start()
  const pending = scheduler.tick()
  poller.start()
  assert.equal(oldCurrent(), false)
  release()
  await pending
  assert.equal(scheduler.pending, 1)
  await scheduler.tick()
  assert.equal(calls, 2)
  assert.equal(scheduler.pending, 1)
  poller.stop()
})
