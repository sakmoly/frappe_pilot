<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Checkbox, FormControl, TextInput } from 'frappe-ui'

import ActionDialog from '@/components/common/ActionDialog.vue'
import AppIcon from '@/components/apps/AppIcon.vue'

import { apiErrorMessage } from '@/api/client'
import { sitesApi } from '@/api/sites'
import { useAppRegistry } from '@/composables/apps/useAppRegistry'
import { openTaskDetailPage } from '@/utils/taskRoute'

const props = defineProps({
  siteName: { type: String, required: true },
})

const open = defineModel('open')

const router = useRouter()
const { titleMap, load: loadRegistry } = useAppRegistry()

const companies = ref([])
const company = ref('')
const preview = ref(null)
const backups = ref([])
const clearMasters = ref(false)
const clearChartOfAccounts = ref(false)
const selectedApps = ref(new Set())
const confirmName = ref('')
const loading = ref(false)
const previewLoading = ref(false)
const error = ref('')

const hasLocalBackup = computed(() =>
  backups.value.some((backup) =>
    backup.files?.some((file) => file.kind === 'database' && file.path),
  ),
)

const companyOptions = computed(() =>
  (Array.isArray(companies.value) ? companies.value : []).map((name) => ({
    label: name,
    value: name,
  })),
)

const appRows = computed(() => preview.value?.apps || [])

const warning = computed(() => {
  if (!hasLocalBackup.value) {
    return {
      title: 'Backup required',
      message: 'Take a local database backup before clearing data. Existing backups are kept on the Backups page.',
    }
  }
  const parts = ['Transactions are removed for the selected company.']
  if (clearMasters.value) parts.push('Master data (customers, items, suppliers, etc.) is deleted.')
  if (clearChartOfAccounts.value) parts.push('Chart of accounts is deleted.')
  parts.push('Company settings stay. This cannot be undone except by restoring a backup.')
  return {
    title: 'Selected data will be permanently deleted',
    message: parts.join(' '),
  }
})

const canConfirm = computed(() => {
  if (!company.value || !hasLocalBackup.value) return false
  if (selectedApps.value.size === 0) return false
  if (confirmName.value !== props.siteName) return false
  return true
})

const reset = () => {
  company.value = ''
  preview.value = null
  clearMasters.value = false
  clearChartOfAccounts.value = false
  selectedApps.value = new Set()
  confirmName.value = ''
  error.value = ''
}

const toggleApp = (app) => {
  const next = new Set(selectedApps.value)
  next.has(app) ? next.delete(app) : next.add(app)
  selectedApps.value = next
}

const toggleAllApps = () => {
  const names = appRows.value.map((row) => row.app)
  selectedApps.value =
    selectedApps.value.size === names.length ? new Set() : new Set(names)
}

watch(open, async (visible) => {
  if (!visible) return
  reset()
  loading.value = false
  previewLoading.value = false
  loadRegistry()
  try {
    const [companyList, backupList] = await Promise.all([
      sitesApi.dataClearing.companies(props.siteName),
      sitesApi.backups.list(props.siteName, 10),
    ])
    companies.value = companyList
    backups.value = backupList
    if (companyList.length === 1) company.value = companyList[0]
  } catch (e) {
    error.value = e.message || 'Could not load data clearing options.'
    companies.value = []
    backups.value = []
  }
})

watch(company, async (value) => {
  preview.value = null
  selectedApps.value = new Set()
  if (!value) return
  previewLoading.value = true
  error.value = ''
  try {
    preview.value = await sitesApi.dataClearing.preview(props.siteName, value)
    selectedApps.value = new Set((preview.value?.apps || []).map((row) => row.app))
  } catch (e) {
    error.value = e.message || 'Could not load preview.'
  } finally {
    previewLoading.value = false
  }
})

const confirm = async () => {
  if (!canConfirm.value) return
  loading.value = true
  error.value = ''
  try {
    const data = await sitesApi.dataClearing.clear(props.siteName, {
      company: company.value,
      clear_transactions: true,
      clear_masters: clearMasters.value,
      clear_chart_of_accounts: clearChartOfAccounts.value,
      included_apps: [...selectedApps.value],
    })
    if (data.task_id) {
      open.value = false
      openTaskDetailPage(router, data.task_id)
    } else error.value = apiErrorMessage(data, 'Failed to clear site data.')
  } catch (e) {
    error.value = e.message || 'Failed to clear site data.'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <ActionDialog
    v-model:open="open"
    title="Clear Site Data"
    size="lg"
    :subject="{
      label: siteName,
      description: 'Remove transactions and optional master data for one company',
      icon: 'lucide-eraser',
    }"
    :warning="warning"
    :error="error"
    confirm-label="Clear data"
    confirm-theme="red"
    :loading="loading"
    :disabled="!canConfirm"
    @confirm="confirm"
  >
    <div class="space-y-4">
      <FormControl
        v-model="company"
        label="Company"
        type="select"
        :options="companyOptions"
        :disabled="!companyOptions.length"
      />

      <div class="flex flex-col gap-2">
        <label class="flex items-center gap-2 cursor-default opacity-80">
          <Checkbox :model-value="true" disabled />
          <span class="text-ink-gray-7 text-sm">Clear transactions</span>
        </label>
        <label class="flex items-center gap-2 cursor-pointer">
          <Checkbox v-model="clearMasters" />
          <span class="text-ink-gray-7 text-sm">Clear master data (customers, items, suppliers, …)</span>
        </label>
        <label class="flex items-center gap-2 cursor-pointer">
          <Checkbox v-model="clearChartOfAccounts" />
          <span class="text-ink-gray-7 text-sm">Clear chart of accounts</span>
        </label>
      </div>

      <div v-if="previewLoading" class="text-ink-gray-5 text-sm">Loading document counts…</div>

      <div v-else-if="appRows.length" class="flex flex-col gap-2">
        <div class="flex items-center justify-between">
          <span class="text-ink-gray-5 text-sm">
            {{ selectedApps.size }} of {{ appRows.length }} apps selected
          </span>
          <button type="button" class="text-ink-gray-6 text-sm hover:text-ink-gray-8" @click="toggleAllApps">
            {{ selectedApps.size === appRows.length ? 'Unselect all' : 'Select all' }}
          </button>
        </div>
        <div class="flex flex-col gap-2 max-h-56 overflow-y-auto">
          <button
            v-for="row in appRows"
            :key="row.app"
            type="button"
            role="checkbox"
            :aria-checked="selectedApps.has(row.app)"
            class="flex items-center gap-2.5 pr-2 text-left"
            @click="toggleApp(row.app)"
          >
            <AppIcon :name="row.app" size="lg" />
            <span class="flex-1 min-w-0">
              <p class="font-medium text-ink-gray-8 text-sm truncate">
                {{ titleMap[row.app] || row.app }}
              </p>
              <p class="text-ink-gray-5 text-p-xs">
                {{ row.document_count.toLocaleString() }} documents
              </p>
            </span>
            <Checkbox
              :model-value="selectedApps.has(row.app)"
              class="pointer-events-none shrink-0"
              tabindex="-1"
              aria-hidden="true"
            />
          </button>
        </div>
      </div>

      <TextInput v-model="confirmName" :placeholder="siteName" class="w-full">
        <template #label>
          <span class="text-sm break-all">Type {{ siteName }} to confirm</span>
        </template>
      </TextInput>
    </div>
  </ActionDialog>
</template>
