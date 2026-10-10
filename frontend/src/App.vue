<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { version as appVersion } from '../package.json'
import { createJobPoller } from './jobPolling'

declare global {
  interface Window { pywebview?: { api: { choose_directory(initial: string, title: string): Promise<string | null> } } }
}

interface Progress {
  kind: string; total: number; completed: number; current_name: string;
  current_bytes: number; current_size: number; phase: string; stop_requested: boolean
}

interface FileItem {
  id: string; name: string; source: string; target: string; category: string;
  size: number; selected: boolean; warning: string; status: string; error?: string; undo_error?: string
}
interface Task {
  id: string; source: string; target: string; created_at: string; status: string;
  files: FileItem[]; warnings: string[]; mode: string; recursive: boolean;
  selected_ids?: string[]; category_filter?: string; saved_at?: string
  progress?: Progress
}
const source = ref('')
const target = ref('')
const mode = ref('all')
const recursive = ref(false)
const busy = ref('')
const error = ref('')
const message = ref('')
const task = ref<Task | null>(null)
const history = ref<Task[]>([])
const drafts = ref<Task[]>([])
const resultsPanel = ref<HTMLElement | null>(null)
const selection = ref<string[]>([])
const filter = ref('全部')
const running = computed(() => ['running', 'undoing'].includes(task.value?.status ?? ''))
const tracking = ref(false)
const locked = computed(() => !!busy.value || running.value || tracking.value)
const failedCount = computed(() => task.value?.files.filter(f => f.status === 'failed').length ?? 0)
const pendingCount = computed(() => task.value?.files.filter(f => f.status === 'pending').length ?? 0)
const progressPercent = computed(() => {
  const p = task.value?.progress
  if (!p?.total) return 0
  return Math.min(100, Math.floor(100 * (p.completed + (p.current_size ? Math.min(.99, p.current_bytes / p.current_size) : 0)) / p.total))
})
const categories = computed(() => ['全部', ...new Set(task.value?.files.map(f => f.category) ?? [])])
const visible = computed(() => task.value?.files.filter(f => filter.value === '全部' || f.category === filter.value) ?? [])
const chosen = computed(() => task.value?.files.filter(f => selection.value.includes(f.id)) ?? [])
const totalSize = computed(() => chosen.value.reduce((sum, f) => sum + f.size, 0))
const preview = computed(() => ['preview', 'draft'].includes(task.value?.status ?? ''))
const draftChanged = computed(() => {
  if (task.value?.status !== 'draft') return false
  const saved = new Set(task.value.selected_ids ?? [])
  return saved.size !== selection.value.length || selection.value.some(id => !saved.has(id)) ||
    filter.value !== (task.value.category_filter ?? '全部')
})
const outcome = computed(() => {
  const files = task.value?.files ?? []
  return `成功 ${files.filter(f => f.status === 'moved').length} · 失败 ${files.filter(f => f.status === 'failed').length} · 跳过 ${files.filter(f => f.status === 'skipped').length}`
})
function size(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`
}
function label(status: string) {
  return ({ preview: '临时预览', draft: '已保存草稿', running: '执行中', undoing: '撤销中', stopped: '已安全停止', queued: '等待处理', pending: '待继续', copying: '复制中', restoring: '恢复中', copied: '校验完成', restore_copied: '校验完成', completed: '任务已结束', moved: '已移动', planned: '待整理',
    skipped: '已跳过', failed: '失败', undone: '已撤销', undo_partial: '部分撤销' } as Record<string, string>)[status] ?? status
}
async function api<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, body === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  })
  const data = await response.json()
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '请求失败，请检查输入。')
  return data
}
async function refresh() {
  const [records, savedDrafts] = await Promise.all([api<Task[]>('/tasks'), api<Task[]>('/drafts')])
  history.value = records; drafts.value = savedDrafts
}
function load(t: Task) {
  task.value = t
  filter.value = t.status === 'draft' ? t.category_filter ?? '全部' : '全部'
  selection.value = t.status === 'draft' ? [...t.selected_ids ?? []] :
    t.files.filter(f => f.selected && f.status === 'planned').map(f => f.id)
  if (['preview', 'draft'].includes(t.status)) {
    source.value = t.source; target.value = t.target; mode.value = t.mode; recursive.value = t.recursive
  }
}

async function chooseDirectory(which: 'source' | 'target') {
  if (locked.value) return
  await run('目录选择窗口已打开，请选择文件夹…', async () => {
    const initial = which === 'source' ? source.value : target.value || source.value
    const title = which === 'source' ? '选择要整理的文件夹' : '选择归档位置'
    const path = window.pywebview ? await window.pywebview.api.choose_directory(initial, title) :
      (await api<{path: string | null}>('/directories/choose', {initial, title})).path
    if (path) {
      if (which === 'source') { source.value = path; target.value = '' }
      else target.value = path
    }
  })
}

const jobPoller = createJobPoller(async isCurrent => {
  const id = task.value?.id
  if (!id) return true
  const result = await api<{status: string; progress: Progress}>(`/tasks/${id}/progress`)
  if (!isCurrent() || task.value?.id !== id) return true
  task.value.status = result.status; task.value.progress = result.progress
  if (['running', 'undoing'].includes(result.status)) {
    error.value = ''
    return false
  }
  // Keep controls locked and polling active until every final request succeeds.
  const [finished, records, savedDrafts] = await Promise.all([
    api<Task>(`/tasks/${id}`), api<Task[]>('/tasks'), api<Task[]>('/drafts'),
  ])
  if (!isCurrent() || task.value?.id !== id) return true
  load(finished); history.value = records; drafts.value = savedDrafts
  error.value = ''
  if (['running', 'undoing'].includes(finished.status)) return false
  tracking.value = false
  message.value = finished.status === 'stopped' ? '已安全停止：当前文件已处理完，未处理文件可点击继续。' :
    finished.status === 'undone' ? '撤销完成，文件已恢复原位置。' :
    `任务已结束。${outcome.value}${finished.status === 'undo_partial' ? '；部分文件未恢复，请查看原因。' : ''}`
  return true
}, e => { error.value = `结果连接中断，将自动重试：${e instanceof Error ? e.message : e}` })

function trackJob() {
  tracking.value = true
  jobPoller.start()
}

function startAction(action: 'execute' | 'undo' | 'retry' | 'resume', record?: Task) {
  const chosenTask = record ?? task.value
  if (!chosenTask || locked.value) return
  run('正在启动文件任务…', async () => {
    load(await api<Task>(`/tasks/${chosenTask.id}/${action}`, action === 'execute' ? {selected_ids: selection.value} : {}))
    trackJob(); await revealResults()
    message.value = '任务在本机后台执行；可安全停止，停止前会完成当前文件。'
  })
}

function stopJob() {
  if (!task.value || !running.value || task.value.progress?.stop_requested) return
  const id = task.value.id
  run('正在申请安全停止…', async () => {
    const state = await api<{progress: Progress}>(`/tasks/${id}/stop`, {})
    if (task.value?.id === id) task.value.progress = state.progress
    message.value = '已申请停止，正在完成当前文件的复制和校验，请稍候。'
  })
}
async function revealResults() {
  await nextTick()
  resultsPanel.value?.focus({ preventScroll: true })
  resultsPanel.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
function viewRecord(record: Task) {
  if (locked.value) return
  run('正在打开记录…', async () => {
    load(await api<Task>(`/tasks/${record.id}`))
    message.value = record.status === 'draft' ? '已恢复草稿的勾选和分类筛选，可以继续选择或执行整理。' : '已打开整理记录，下面显示本次文件的原位置、目标位置与处理结果。'
    await revealResults()
  })
}
function saveDraft() {
  if (!task.value || !preview.value) return
  const id = task.value.id
  run('正在保存草稿…', async () => {
    load(await api<Task>(`/tasks/${id}/draft`, { selected_ids: selection.value, category_filter: filter.value }))
    await refresh()
    message.value = '草稿已保存到本机。刷新页面或重启服务后，会自动恢复最近保存的草稿。'
  })
}
async function run(action: string, work: () => Promise<void>) {
  if (busy.value) return
  busy.value = action; error.value = ''; message.value = ''
  try { await work() } catch (e) { error.value = e instanceof Error ? e.message : String(e) }
  finally { busy.value = '' }
}
function scan() {
  run('正在扫描文件…', async () => {
    const destination = target.value.trim() || `${source.value.trim().replace(/[\\/]+$/, '')}\\Archive`
    load(await api<Task>('/scan', { source: source.value.trim(), target: destination, mode: mode.value, recursive: recursive.value }))
    message.value = `找到 ${task.value?.files.length} 个候选文件。扫描不会写入历史；需要下次继续时请保存草稿。`
  })
}
function execute() {
  if (!task.value || !selection.value.length) return
  startAction('execute')
}
function undo(t: Task) {
  startAction('undo', t)
}
function selectDocuments() {
  const documents = new Set(['Word文档', 'PDF文档', 'Excel表格', '演示文稿'])
  selection.value = task.value?.files.filter(f => documents.has(f.category)).map(f => f.id) ?? []
}
function selectAll() {
  selection.value = task.value?.files.map(f => f.id) ?? []
}
onMounted(() => run('正在连接本机服务…', async () => {
  await refresh()
  const active = await api<{id: string} | null>('/active')
  if (active) {
    load(await api<Task>(`/tasks/${active.id}`)); trackJob()
    message.value = '已连接正在运行的任务。'
  } else if (drafts.value[0]) {
    load(await api<Task>(`/tasks/${drafts.value[0].id}`))
    message.value = '已自动恢复最近保存的草稿，包括勾选文件和分类筛选。执行前仍会检查文件是否变化。'
  }
}))
onUnmounted(() => { jobPoller.stop() })
</script>

<template>
  <div class="shell">
    <aside>
      <div class="brand"><span class="logo">▤</span><div>拾序 <small>文件整理助手</small></div></div>
      <div class="nav active">▦ <span>文件整理</span></div>
      <a class="nav" href="#history">◷ <span>整理记录</span></a>
      <div class="aside-note"><span class="dot"></span>本机文件处理<p>文件在你的电脑上整理。<br>先预览，再移动，可撤销。</p></div>
    </aside>
    <main>
      <header><div><div class="eyebrow">让文件各归其位</div><h1>给文件腾出秩序</h1><p>选择一个文件夹，把散落的文档和安装包收进合适的位置。</p></div><span class="badge">本机文件整理 · v{{ appVersion }}</span></header>
      <section class="panel setup">
        <div class="section-title"><h2><span class="step">01</span>选择整理范围</h2><span>扫描不会移动文件</span></div>
        <form @submit.prevent="scan">
          <div class="fields">
            <label>源文件夹<div class="path-input"><input v-model="source" required placeholder="例如 D:\download 或 D:\" :disabled="locked" /><button type="button" class="secondary" :disabled="locked" @click="chooseDirectory('source')">选择目录</button></div><small>粘贴文件夹的完整路径；默认仅扫描当前层级。</small></label>
            <label>归档位置<div class="path-input"><input v-model="target" placeholder="留空则放入源文件夹内的 Archive" :disabled="locked" /><button type="button" class="secondary" :disabled="locked" @click="chooseDirectory('target')">选择目录</button></div><small>自动创建的分类目录使用英文；保留原文件名。</small></label>
          </div>
          <div class="rules">
            <button v-for="rule in [{ id: 'documents', icon: '▤', name: '办公文档', desc: 'Word / PDF / Excel / PPT' }, { id: 'installers', icon: '↓', name: '安装包候选', desc: 'EXE / MSI / MSIX / ISO' }, { id: 'all', icon: '▦', name: '全部文件', desc: '文档 / 压缩包 / 媒体 / 其他' }]" :key="rule.id" type="button" class="rule" :class="{ selected: mode === rule.id }" :disabled="locked" @click="mode = rule.id">
              <span class="rule-icon">{{ rule.icon }}</span><strong>{{ rule.name }}</strong><small>{{ rule.desc }}</small>
            </button>
          </div>
          <p class="muted">全部文件模式会归类当前层级的普通文件；字体放入 Fonts，未知类型及无扩展名文件放入 Other。默认不进入子文件夹。</p>
          <div class="setup-footer"><label class="check"><input v-model="recursive" type="checkbox" :disabled="locked" />包含子文件夹</label><button class="primary" :disabled="locked">扫描并预览 <span>→</span></button></div>
        </form>
      </section>
      <div v-if="busy" class="notice" role="status">{{ busy }}</div>
      <div v-if="error" class="notice danger" role="alert">{{ error }}</div>
      <div v-if="message" class="notice success" role="status">{{ message }}</div>
      <section id="results" ref="resultsPanel" class="panel results" tabindex="-1" aria-label="文件预览和整理记录详情">
        <div class="section-title"><h2><span class="step">02</span>{{ preview || !task ? '核对整理预览' : '查看整理结果' }}</h2><span v-if="task">{{ task.files.length }} 个文件 · {{ label(task.status) }}<template v-if="task.status === 'completed'"> · {{ outcome }}</template></span></div>
        <div v-if="!task" class="empty"><div class="empty-icon">▱</div><h3>从一个文件夹开始</h3><p>扫描后，这里会展示每个文件的原位置和归档位置。<br>安装包候选需要手动勾选确认。</p></div>
        <template v-else>
          <p class="muted">{{ new Date(task.created_at).toLocaleString('zh-CN') }} · 记录 {{ task.id.slice(0, 8) }}</p>
          <div class="preview-note">{{ task.source }} → {{ task.target }}<p>按类型归类可能影响文档中的相对链接。安装包仅按扩展名识别，请确认可移动后勾选。</p></div>
          <div v-if="running && task.progress" class="job-progress" role="status"><div class="job-head"><strong>{{ task.status === 'undoing' ? '正在恢复文件' : '正在整理文件' }} · {{ task.progress.completed }} / {{ task.progress.total }}</strong><button class="secondary" :disabled="!!busy || task.progress.stop_requested" @click="stopJob">{{ task.progress.stop_requested ? '等待当前文件完成…' : '安全停止' }}</button></div><progress :value="progressPercent" max="100" :aria-label="`已处理 ${progressPercent}%`"></progress><p>{{ task.progress.current_name || '正在准备…' }} · {{ task.progress.phase === 'verifying' ? '校验内容' : '复制文件' }} <template v-if="task.progress.current_size">· {{ size(task.progress.current_bytes) }} / {{ size(task.progress.current_size) }}</template></p><small>停止会完成当前文件；已处理的文件保留撤销记录。</small></div>
          <div v-if="!preview && !running && (failedCount || pendingCount)" class="notice danger">失败 {{ failedCount }} 个 · 待继续 {{ pendingCount }} 个<div class="result-actions"><button v-if="failedCount && ['completed', 'stopped'].includes(task.status)" class="secondary" :disabled="locked" @click="startAction('retry')">重试失败项（{{ failedCount }}）</button><button v-if="pendingCount && task.status === 'stopped'" class="secondary" :disabled="locked" @click="startAction('resume')">继续未处理文件（{{ pendingCount }}）</button></div></div>
          <div v-for="warning in task.warnings" :key="warning" class="notice danger">{{ warning }}</div>
          <div class="toolbar"><div class="tabs"><button v-for="category in categories" :key="category" :class="{ current: filter === category }" @click="filter = category">{{ category }}</button></div><div v-if="preview" class="selection"><button :disabled="!!busy || !task.files.length" @click="selectAll">一键全选（含 EXE）</button><button :disabled="locked" @click="selectDocuments">只选办公文件</button><button :disabled="locked" @click="selection = []">取消全选</button></div></div>
          <div v-if="!task.files.length" class="empty"><h3>未找到匹配的文件</h3><p>可以尝试切换规则或包含子文件夹。</p></div>
          <div v-else class="table-wrap"><table><thead><tr><th v-if="preview">选择</th><th>文件</th><th>归档位置</th><th>大小</th><th>状态</th></tr></thead><tbody><tr v-for="file in visible" :key="file.id"><td v-if="preview"><input v-model="selection" type="checkbox" :value="file.id" :disabled="locked" :aria-label="`选择 ${file.name}`" /></td><td><strong>{{ file.name }}</strong><small class="path" :title="file.source">{{ file.source }}</small><small v-if="file.warning" class="warning">{{ file.warning }}</small></td><td><span class="category">{{ file.category }}</span><small class="path" :title="file.target">{{ file.target }}</small><small v-if="file.error || file.undo_error" class="warning">{{ file.error || file.undo_error }}</small></td><td class="nowrap">{{ size(file.size) }}</td><td class="nowrap">{{ label(file.status) }}</td></tr></tbody></table></div>
          <div v-if="preview" class="result-footer"><span>已选 <strong>{{ chosen.length }}</strong> 个文件 · {{ size(totalSize) }}<small class="draft-note">{{ task.status === 'draft' ? (draftChanged ? '当前选择有修改，请再次保存草稿。' : '当前草稿已保存，可下次继续。') : '临时预览，刷新或重启后不保留；可主动保存草稿。' }}</small></span><div class="result-actions"><button class="secondary" :disabled="locked" @click="saveDraft">{{ task.status === 'draft' ? '更新草稿' : '保存草稿' }}</button><button class="primary" :disabled="!!busy || !chosen.length" @click="execute">整理所选文件 →</button></div></div>
          <div v-else-if="!running && task.files.some(f => f.status === 'moved')" class="result-footer"><span>撤销会检查文件内容，并保留已有同名文件。</span><button class="secondary" :disabled="locked" @click="undo(task)">撤销本次整理</button></div>
        </template>
      </section>
      <section v-if="drafts.length" class="panel drafts"><div class="section-title"><h2>保存的草稿</h2><span>主动保存，重启后继续</span></div><div v-for="draft in drafts" :key="draft.id" class="history-row" :class="{ 'record-active': task?.id === draft.id }" :data-draft-id="draft.id"><div><strong>{{ draft.source }}</strong><small>{{ new Date(draft.saved_at ?? draft.created_at).toLocaleString('zh-CN') }} · 已选 {{ draft.selected_ids?.length ?? 0 }} / {{ draft.files.length }} 个文件</small></div><div class="history-actions"><button :disabled="locked" @click="viewRecord(draft)">继续整理</button></div></div></section>
      <section id="history" class="panel history"><div class="section-title"><h2><span class="step">03</span>最近整理记录</h2><span>仅记录实际执行的整理</span></div><p v-if="!history.length" class="muted">还没有执行过整理。扫描不会自动保存到历史。</p><div v-for="record in history" :key="record.id" class="history-row" :class="{ 'record-active': task?.id === record.id }" :data-record-id="record.id"><div><strong>{{ record.source }}</strong><small>{{ new Date(record.created_at).toLocaleString('zh-CN') }} · {{ record.files.length }} 个文件 · {{ label(record.status) }}</small></div><div class="history-actions"><button :disabled="locked" @click="viewRecord(record)">{{ task?.id === record.id ? '正在查看' : '查看' }}</button><button v-if="record.files.some(f => f.status === 'moved') && record.status !== 'running'" :disabled="locked" @click="undo(record)">撤销</button></div></div></section>
      <footer>拾序 · 每一次整理，都有迹可循。任务在本机执行，历史记录可用于撤销。</footer>
    </main>
  </div>
</template>
