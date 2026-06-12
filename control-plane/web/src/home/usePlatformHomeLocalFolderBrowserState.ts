import { useState } from 'react'
import type { BrowseEntry } from './types'

export function usePlatformHomeLocalFolderBrowserState() {
  const [localPath, setLocalPath] = useState('')
  const [browsePath, setBrowsePath] = useState('/opt/workstation/repos')
  const [browseEntries, setBrowseEntries] = useState<BrowseEntry[]>([])
  const [loadingBrowse, setLoadingBrowse] = useState(false)
  const [browseError, setBrowseError] = useState('')

  return {
    localPath,
    setLocalPath,
    browsePath,
    setBrowsePath,
    browseEntries,
    setBrowseEntries,
    loadingBrowse,
    setLoadingBrowse,
    browseError,
    setBrowseError,
  }
}
