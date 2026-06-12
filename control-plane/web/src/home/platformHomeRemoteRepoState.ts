import { useState } from 'react'
import type { GitHubRepo } from './types'

export function usePlatformHomeRemoteRepoState() {
  const [items, setItems] = useState<GitHubRepo[]>([])
  const [selectedName, setSelectedName] = useState('')
  const [filterText, setFilterText] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  return {
    items,
    setItems,
    selectedName,
    setSelectedName,
    filterText,
    setFilterText,
    loading,
    setLoading,
    error,
    setError,
  }
}
