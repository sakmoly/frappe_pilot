import { toast } from 'frappe-ui'

import { useBenches } from '@/composables/benches/useBenches'

export const useBenchRestart = () => {
  const { control, controlLoading, error } = useBenches()

  const restart = async (name: string, { confirm = true } = {}) => {
    if (
      confirm &&
      !window.confirm(`Restart bench "${name}"? Sites may briefly stop responding.`)
    ) {
      return false
    }
    const ok = await control(name, 'restart')
    if (ok) toast.success(`Bench "${name}" restarted`)
    else if (error.value) toast.error(error.value)
    return ok
  }

  return { restart, controlLoading }
}
