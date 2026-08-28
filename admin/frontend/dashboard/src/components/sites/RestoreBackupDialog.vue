<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { FormControl, TextInput } from 'frappe-ui'

import ActionDialog from '@/components/common/ActionDialog.vue'

import { apiErrorMessage } from '@/api/client'
import { sitesApi } from '@/api/sites'
import { fmtDateTime } from '@/utils/taskFormat'
import { openTaskDetailPage } from '@/utils/taskRoute'

const props = defineProps({
  sourceSite: { type: String, required: true },
  backup: { type: Object, default: null },
})

const open = defineModel('open')

const router = useRouter()

const targetMode = ref('same')
const targetSite = ref('')
const adminPassword = ref('')
const sites = ref([])
const loading = ref(false)
const error = ref('')

const targetModeOptions = computed(() => [
  { label: `This site (${props.sourceSite})`, value: 'same' },
  { label: 'Another site', value: 'other' },
])

const hasLocalDatabase = computed(() =>
  Boolean(props.backup?.files?.find((file) => file.kind === 'database' && file.path)),
)

const effectiveTarget = computed(() =>
  targetMode.value === 'same' ? props.sourceSite : targetSite.value.trim(),
)

const targetExists = computed(() =>
  Boolean(effectiveTarget.value && sites.value.some((site) => site.name === effectiveTarget.value)),
)

const needsPassword = computed(
  () => targetMode.value === 'other' && effectiveTarget.value && !targetExists.value,
)

const canConfirm = computed(() => {
  if (!hasLocalDatabase.value || !props.backup) return false
  if (targetMode.value === 'other') {
    if (!effectiveTarget.value) return false
    if (needsPassword.value && !adminPassword.value.trim()) return false
  }
  return true
})

const backupLabel = computed(() =>
  props.backup ? fmtDateTime(props.backup.created_at) : '',
)

const warning = computed(() => {
  if (!hasLocalDatabase.value) {
    return {
      title: 'Local backup required',
      message:
        'Only backups stored on this server can be restored here. Download the database from offsite storage first.',
    }
  }
  if (targetMode.value === 'same') {
    return {
      title: 'This replaces current site data',
      message: `${props.sourceSite} is restored to the state captured in this backup. Current data is overwritten.`,
    }
  }
  if (targetExists.value) {
    return {
      title: 'This replaces the target site data',
      message: `${effectiveTarget.value} is restored from ${props.sourceSite}'s backup. Current data on the target site is overwritten.`,
    }
  }
  return {
    title: 'A new site will be created',
    message: `${effectiveTarget.value} is created and populated from this backup.`,
  }
})

const reset = () => {
  targetMode.value = 'same'
  targetSite.value = ''
  adminPassword.value = ''
  error.value = ''
}

watch(open, async (visible) => {
  if (!visible) return
  reset()
  try {
    sites.value = await sitesApi.list()
  } catch {
    sites.value = []
  }
})

const confirm = async () => {
  if (!props.backup || !canConfirm.value) return
  loading.value = true
  error.value = ''
  try {
    const payload = {}
    if (targetMode.value === 'other') payload.target_site = effectiveTarget.value
    if (needsPassword.value) payload.admin_password = adminPassword.value
    const data = await sitesApi.backups.restore(props.sourceSite, props.backup.timestamp, payload)
    if (data.task_id) {
      open.value = false
      openTaskDetailPage(router, data.task_id)
    } else error.value = apiErrorMessage(data, 'Restore failed.')
  } catch (e) {
    error.value = e.message || 'Restore failed.'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <ActionDialog
    v-model:open="open"
    title="Restore Backup"
    :subject="{
      label: backupLabel,
      description: `From ${sourceSite}`,
      icon: 'lucide-history',
    }"
    :warning="warning"
    :error="error"
    confirm-label="Restore"
    confirm-theme="red"
    :loading="loading"
    :disabled="!canConfirm"
    @confirm="confirm"
  >
    <div class="space-y-4">
      <FormControl
        v-model="targetMode"
        label="Restore to"
        type="select"
        :options="targetModeOptions"
      />

      <TextInput
        v-if="targetMode === 'other'"
        v-model="targetSite"
        placeholder="site.example.com"
        class="w-full"
      >
        <template #label>Target site</template>
        <template #description>
          Enter an existing site name to overwrite it, or a new hostname to create a site.
        </template>
      </TextInput>

      <TextInput
        v-if="needsPassword"
        v-model="adminPassword"
        type="password"
        placeholder="Administrator password"
        class="w-full"
      >
        <template #label>Administrator password</template>
      </TextInput>
    </div>
  </ActionDialog>
</template>
