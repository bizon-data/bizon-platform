import { useState, useEffect } from 'react'
import { useNavigate, Link, useParams } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { Button, Card, CardHeader, CardTitle, CardContent, TagInput, PageLoader } from '../components/ui'
import { DestinationConfigForm, isDestinationConfigValid } from '../components/DestinationConfigForm'
import { useToast } from '../contexts/ToastContext'
import { validateCron } from '../utils/cron'
import {
  useCreatePipeline,
  useUpdatePipeline,
  usePipeline,
  useSourceConnectors,
  useDestinationConnectors,
  useCustomSources,
  useTags,
} from '../hooks'
import type { CreatePipelineRequest } from '../api'

type SourceType = 'builtin' | 'custom'

const SCHEDULE_PRESETS = [
  { label: 'No schedule (manual only)', value: '' },
  { label: 'Every hour', value: '0 * * * *' },
  { label: 'Every 6 hours', value: '0 */6 * * *' },
  { label: 'Every day at midnight', value: '0 0 * * *' },
  { label: 'Every day at 9am', value: '0 9 * * *' },
  { label: 'Every Monday at 9am', value: '0 9 * * 1' },
  { label: 'Every month (1st at midnight)', value: '0 0 1 * *' },
  { label: 'Custom...', value: 'custom' },
]

interface FormData {
  name: string
  sourceType: SourceType
  sourceName: string
  sourceStream: string
  customSourceName: string
  customSourceStream: string
  customSourceFilePath: string
  destinationName: string
  destinationConfig: Record<string, unknown>
  schedulePreset: string
  scheduleCustom: string
  enabled: boolean
  tags: string[]
}

const initialFormData: FormData = {
  name: '',
  sourceType: 'builtin',
  sourceName: '',
  sourceStream: '',
  customSourceName: '',
  customSourceStream: '',
  customSourceFilePath: '',
  destinationName: '',
  destinationConfig: {},
  schedulePreset: '',
  scheduleCustom: '',
  enabled: true,
  tags: [],
}

export function PipelineCreatePage() {
  const { id } = useParams<{ id: string }>()
  const isEditMode = !!id
  const navigate = useNavigate()
  const { addToast } = useToast()
  const createPipeline = useCreatePipeline()
  const updatePipeline = useUpdatePipeline()
  const { data: pipeline, isLoading: isPipelineLoading } = usePipeline(id || '')
  const { data: sources } = useSourceConnectors()
  const { data: destinations } = useDestinationConnectors()
  const { data: customSources } = useCustomSources()
  const { data: existingTags } = useTags()

  const [formData, setFormData] = useState<FormData>(initialFormData)
  const [isInitialized, setIsInitialized] = useState(!isEditMode)
  const [cronError, setCronError] = useState<string | null>(null)

  // Populate form when editing
  useEffect(() => {
    if (isEditMode && pipeline && !isInitialized) {
      const config = pipeline.config
      const sourceConfig = config.source || {}
      const isCustomSource = !!sourceConfig.source_file_path

      // Check if schedule matches a preset
      const schedule = pipeline.schedule || ''
      const matchingPreset = SCHEDULE_PRESETS.find(p => p.value === schedule && p.value !== 'custom')
      const schedulePreset = matchingPreset ? schedule : (schedule ? 'custom' : '')
      const scheduleCustom = matchingPreset ? '' : schedule

      setFormData({
        name: pipeline.name,
        sourceType: isCustomSource ? 'custom' : 'builtin',
        sourceName: isCustomSource ? '' : (sourceConfig.name || ''),
        sourceStream: isCustomSource ? '' : (sourceConfig.stream || ''),
        customSourceName: isCustomSource ? (sourceConfig.name || '') : '',
        customSourceStream: isCustomSource ? (sourceConfig.stream || '') : '',
        customSourceFilePath: sourceConfig.source_file_path || '',
        destinationName: config.destination?.name || '',
        destinationConfig: config.destination?.config || {},
        schedulePreset,
        scheduleCustom,
        enabled: pipeline.enabled,
        tags: pipeline.tags || [],
      })
      setIsInitialized(true)
    }
  }, [isEditMode, pipeline, isInitialized])

  const selectedSource = sources?.find((s) => s.name === formData.sourceName)
  const selectedCustomSource = customSources?.find((s) => s.name === formData.customSourceName)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    // Validate cron expression
    if (cronError) {
      addToast({ type: 'error', message: 'Please fix the schedule before saving' })
      return
    }

    // Validate destination config
    if (formData.destinationName && !isDestinationConfigValid(formData.destinationName, formData.destinationConfig)) {
      addToast({ type: 'error', message: 'Please fill in all required destination fields' })
      return
    }

    const isCustom = formData.sourceType === 'custom'
    const schedule = formData.schedulePreset === 'custom'
      ? formData.scheduleCustom
      : formData.schedulePreset

    // The form only edits a few fields; keep everything else (auth, transforms, engine, source
    // options) from the stored config so saving doesn't wipe settings made through the API.
    const existing = isEditMode ? pipeline?.config : undefined
    const sourceName = isCustom ? formData.customSourceName : formData.sourceName
    const sourceStream = isCustom ? formData.customSourceStream : formData.sourceStream
    const existingSource =
      existing?.source &&
      existing.source.name === sourceName &&
      existing.source.stream === sourceStream &&
      !!existing.source.source_file_path === isCustom
        ? existing.source
        : undefined
    const existingDestination =
      existing?.destination?.name === formData.destinationName ? existing.destination : undefined

    const request: CreatePipelineRequest = {
      name: formData.name,
      config: {
        ...existing,
        name: formData.name,
        source: isCustom
          ? {
              ...existingSource,
              source_file_path: formData.customSourceFilePath,
              name: sourceName,
              stream: sourceStream,
            }
          : {
              ...existingSource,
              name: sourceName,
              stream: sourceStream,
              authentication: existingSource?.authentication ?? {
                type: 'api_key',
                params: { token: 'placeholder' },
              },
            },
        destination: {
          ...existingDestination,
          name: formData.destinationName,
          config: formData.destinationConfig,
        },
      },
      schedule: schedule || undefined,
      enabled: formData.enabled,
      tags: formData.tags.length > 0 ? formData.tags : undefined,
    }

    try {
      if (isEditMode && id) {
        await updatePipeline.mutateAsync({ id, data: request })
        navigate(`/pipelines/${id}`)
      } else {
        await createPipeline.mutateAsync(request)
        navigate('/pipelines')
      }
    } catch (error) {
      // Error already handled by mutation's onError
    }
  }

  const isSubmitting = createPipeline.isPending || updatePipeline.isPending

  if (isEditMode && isPipelineLoading) {
    return <PageLoader />
  }

  const inputClassName =
    'w-full px-3 py-2 bg-bizon-bg border border-bizon-border rounded-lg text-bizon-text focus:outline-none focus:ring-2 focus:ring-bizon-primary'

  return (
    <div className="space-y-6 max-w-2xl mx-auto">
      <div className="flex items-center gap-4">
        <Link to={isEditMode ? `/pipelines/${id}` : '/pipelines'}>
          <Button variant="ghost" size="sm">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <h1 className="text-2xl font-bold text-bizon-text">
          {isEditMode ? 'Edit Pipeline' : 'Create Pipeline'}
        </h1>
      </div>

      <form onSubmit={handleSubmit}>
        <Card>
          <CardHeader>
            <CardTitle>Pipeline Details</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-bizon-text mb-1">Name</label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                className={inputClassName}
                placeholder="my-pipeline"
                required
              />
            </div>

            {/* Source Type Selection */}
            <div>
              <label className="block text-sm font-medium text-bizon-text mb-2">Source Type</label>
              <div className="flex gap-4">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="sourceType"
                    value="builtin"
                    checked={formData.sourceType === 'builtin'}
                    onChange={() =>
                      setFormData({
                        ...formData,
                        sourceType: 'builtin',
                        customSourceName: '',
                        customSourceStream: '',
                        customSourceFilePath: '',
                      })
                    }
                    className="h-4 w-4 text-bizon-primary border-bizon-border bg-bizon-bg focus:ring-bizon-primary"
                  />
                  <span className="text-sm text-bizon-text">Built-in Source</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="sourceType"
                    value="custom"
                    checked={formData.sourceType === 'custom'}
                    onChange={() =>
                      setFormData({
                        ...formData,
                        sourceType: 'custom',
                        sourceName: '',
                        sourceStream: '',
                      })
                    }
                    className="h-4 w-4 text-bizon-primary border-bizon-border bg-bizon-bg focus:ring-bizon-primary"
                  />
                  <span className="text-sm text-bizon-text">Custom Source</span>
                </label>
              </div>
            </div>

            {/* Built-in Source Fields */}
            {formData.sourceType === 'builtin' && (
              <>
                <div>
                  <label className="block text-sm font-medium text-bizon-text mb-1">Source</label>
                  <select
                    value={formData.sourceName}
                    onChange={(e) =>
                      setFormData({ ...formData, sourceName: e.target.value, sourceStream: '' })
                    }
                    className={inputClassName}
                    required
                  >
                    <option value="">Select a source</option>
                    {sources?.map((source) => (
                      <option key={source.name} value={source.name}>
                        {source.name}
                      </option>
                    ))}
                  </select>
                </div>

                {selectedSource && (
                  <div>
                    <label className="block text-sm font-medium text-bizon-text mb-1">Stream</label>
                    <select
                      value={formData.sourceStream}
                      onChange={(e) => setFormData({ ...formData, sourceStream: e.target.value })}
                      className={inputClassName}
                      required
                    >
                      <option value="">Select a stream</option>
                      {selectedSource.streams.map((stream) => (
                        <option key={stream.name} value={stream.name}>
                          {stream.name}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
              </>
            )}

            {/* Custom Source Fields */}
            {formData.sourceType === 'custom' && (
              <>
                <div>
                  <label className="block text-sm font-medium text-bizon-text mb-1">
                    Custom Source
                  </label>
                  {customSources && customSources.length > 0 ? (
                    <select
                      value={formData.customSourceName}
                      onChange={(e) => {
                        const selected = customSources.find((s) => s.name === e.target.value)
                        setFormData({
                          ...formData,
                          customSourceName: e.target.value,
                          customSourceFilePath: selected?.file_path || '',
                          customSourceStream: '',
                        })
                      }}
                      className={inputClassName}
                      required
                    >
                      <option value="">Select a custom source</option>
                      {customSources.map((source) => (
                        <option key={source.name} value={source.name}>
                          {source.name}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <p className="text-sm text-bizon-muted">
                      No custom sources found. Add sources to{' '}
                      <code className="bg-bizon-surface px-1 rounded">custom_sources/</code>{' '}
                      directory.
                    </p>
                  )}
                </div>

                {selectedCustomSource && (
                  <>
                    <div>
                      <label className="block text-sm font-medium text-bizon-text mb-1">
                        File Path
                      </label>
                      <input
                        type="text"
                        value={formData.customSourceFilePath}
                        onChange={(e) =>
                          setFormData({ ...formData, customSourceFilePath: e.target.value })
                        }
                        className={`${inputClassName} font-mono text-sm`}
                        placeholder="/custom_sources/my_source/source.py"
                        required
                      />
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-bizon-text mb-1">
                        Stream
                      </label>
                      <select
                        value={formData.customSourceStream}
                        onChange={(e) =>
                          setFormData({ ...formData, customSourceStream: e.target.value })
                        }
                        className={inputClassName}
                        required
                      >
                        <option value="">Select a stream</option>
                        {selectedCustomSource.streams.map((stream) => (
                          <option key={stream} value={stream}>
                            {stream}
                          </option>
                        ))}
                      </select>
                    </div>
                  </>
                )}
              </>
            )}

            <div>
              <label className="block text-sm font-medium text-bizon-text mb-1">Destination</label>
              <select
                value={formData.destinationName}
                onChange={(e) => setFormData({
                  ...formData,
                  destinationName: e.target.value,
                  destinationConfig: {}, // Reset config when destination changes
                })}
                className={inputClassName}
                required
              >
                <option value="">Select a destination</option>
                {destinations?.map((dest) => (
                  <option key={dest.name} value={dest.name}>
                    {dest.name}
                  </option>
                ))}
              </select>
            </div>

            {formData.destinationName && (
              <div className="pl-4 border-l-2 border-bizon-border">
                <label className="block text-sm font-medium text-bizon-text mb-2">
                  Destination Configuration
                </label>
                <DestinationConfigForm
                  destinationName={formData.destinationName}
                  config={formData.destinationConfig}
                  onChange={(config) => setFormData({ ...formData, destinationConfig: config })}
                />
              </div>
            )}

            <div>
              <label className="block text-sm font-medium text-bizon-text mb-1">
                Schedule
              </label>
              <select
                value={formData.schedulePreset}
                onChange={(e) => {
                  const value = e.target.value
                  setFormData({
                    ...formData,
                    schedulePreset: value,
                    scheduleCustom: value === 'custom' ? formData.scheduleCustom : ''
                  })
                  // Clear cron error when switching away from custom
                  if (value !== 'custom') {
                    setCronError(null)
                  }
                }}
                className={inputClassName}
              >
                {SCHEDULE_PRESETS.map((preset) => (
                  <option key={preset.value} value={preset.value}>
                    {preset.label}{preset.value && preset.value !== 'custom' ? ` (${preset.value})` : ''}
                  </option>
                ))}
              </select>
              {formData.schedulePreset === 'custom' && (
                <div className="mt-2">
                  <input
                    type="text"
                    value={formData.scheduleCustom}
                    onChange={(e) => {
                      const value = e.target.value
                      setFormData({ ...formData, scheduleCustom: value })
                      const result = validateCron(value)
                      setCronError(result.valid ? null : result.error || 'Invalid cron expression')
                    }}
                    className={`${inputClassName} font-mono ${cronError ? 'border-red-500 focus:ring-red-500' : ''}`}
                    placeholder="0 9 * * * (minute hour day month weekday)"
                  />
                  {cronError && (
                    <p className="text-red-500 text-sm mt-1">{cronError}</p>
                  )}
                  <p className="text-xs text-bizon-muted mt-1">
                    Format: minute (0-59) hour (0-23) day (1-31) month (1-12) weekday (0-6, 0=Sun)
                  </p>
                </div>
              )}
            </div>

            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="enabled"
                checked={formData.enabled}
                onChange={(e) => setFormData({ ...formData, enabled: e.target.checked })}
                className="h-4 w-4 rounded border-bizon-border bg-bizon-bg text-bizon-primary focus:ring-bizon-primary"
              />
              <label htmlFor="enabled" className="text-sm text-bizon-text">
                Enable pipeline
              </label>
            </div>

            <div>
              <label className="block text-sm font-medium text-bizon-text mb-1">Tags</label>
              <TagInput
                tags={formData.tags}
                onChange={(tags) => setFormData({ ...formData, tags })}
                suggestions={existingTags || []}
                placeholder="Add tags..."
              />
              <p className="text-xs text-bizon-muted mt-1">
                Press Enter to add a tag. Use tags to group and filter pipelines.
              </p>
            </div>

            <div className="flex justify-end gap-3 pt-4">
              <Link to={isEditMode ? `/pipelines/${id}` : '/pipelines'}>
                <Button type="button" variant="secondary">
                  Cancel
                </Button>
              </Link>
              <Button type="submit" disabled={isSubmitting}>
                {isSubmitting
                  ? isEditMode ? 'Saving...' : 'Creating...'
                  : isEditMode ? 'Save Changes' : 'Create Pipeline'}
              </Button>
            </div>
          </CardContent>
        </Card>
      </form>
    </div>
  )
}
