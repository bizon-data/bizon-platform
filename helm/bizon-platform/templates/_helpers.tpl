{{/*
Expand the name of the chart.
*/}}
{{- define "bizon-platform.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "bizon-platform.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "bizon-platform.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "bizon-platform.labels" -}}
helm.sh/chart: {{ include "bizon-platform.chart" . }}
{{ include "bizon-platform.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "bizon-platform.selectorLabels" -}}
app.kubernetes.io/name: {{ include "bizon-platform.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
API labels
*/}}
{{- define "bizon-platform.api.labels" -}}
{{ include "bizon-platform.labels" . }}
app.kubernetes.io/component: api
{{- end }}

{{/*
API selector labels
*/}}
{{- define "bizon-platform.api.selectorLabels" -}}
{{ include "bizon-platform.selectorLabels" . }}
app.kubernetes.io/component: api
{{- end }}

{{/*
Worker labels
*/}}
{{- define "bizon-platform.worker.labels" -}}
{{ include "bizon-platform.labels" . }}
app.kubernetes.io/component: worker
{{- end }}

{{/*
Worker selector labels
*/}}
{{- define "bizon-platform.worker.selectorLabels" -}}
{{ include "bizon-platform.selectorLabels" . }}
app.kubernetes.io/component: worker
{{- end }}

{{/*
UI labels
*/}}
{{- define "bizon-platform.ui.labels" -}}
{{ include "bizon-platform.labels" . }}
app.kubernetes.io/component: ui
{{- end }}

{{/*
UI selector labels
*/}}
{{- define "bizon-platform.ui.selectorLabels" -}}
{{ include "bizon-platform.selectorLabels" . }}
app.kubernetes.io/component: ui
{{- end }}

{{/*
PostgreSQL labels
*/}}
{{- define "bizon-platform.postgresql.labels" -}}
{{ include "bizon-platform.labels" . }}
app.kubernetes.io/component: postgresql
{{- end }}

{{/*
PostgreSQL selector labels
*/}}
{{- define "bizon-platform.postgresql.selectorLabels" -}}
{{ include "bizon-platform.selectorLabels" . }}
app.kubernetes.io/component: postgresql
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "bizon-platform.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "bizon-platform.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
PostgreSQL host
*/}}
{{- define "bizon-platform.postgresql.host" -}}
{{- if .Values.postgresql.enabled }}
{{- printf "%s-postgresql" (include "bizon-platform.fullname" .) }}
{{- else }}
{{- .Values.externalDatabase.host }}
{{- end }}
{{- end }}

{{/*
PostgreSQL port
*/}}
{{- define "bizon-platform.postgresql.port" -}}
{{- if .Values.postgresql.enabled }}
{{- 5432 }}
{{- else }}
{{- .Values.externalDatabase.port }}
{{- end }}
{{- end }}

{{/*
PostgreSQL database name
*/}}
{{- define "bizon-platform.postgresql.database" -}}
{{- if .Values.postgresql.enabled }}
{{- .Values.postgresql.auth.database }}
{{- else }}
{{- .Values.externalDatabase.database }}
{{- end }}
{{- end }}

{{/*
PostgreSQL username
*/}}
{{- define "bizon-platform.postgresql.username" -}}
{{- if .Values.postgresql.enabled }}
{{- .Values.postgresql.auth.username }}
{{- else }}
{{- .Values.externalDatabase.username }}
{{- end }}
{{- end }}

{{/*
PostgreSQL secret name
*/}}
{{- define "bizon-platform.postgresql.secretName" -}}
{{- if .Values.postgresql.enabled }}
{{- if .Values.postgresql.auth.existingSecret }}
{{- .Values.postgresql.auth.existingSecret }}
{{- else }}
{{- printf "%s-postgresql" (include "bizon-platform.fullname" .) }}
{{- end }}
{{- else }}
{{- if .Values.externalDatabase.existingSecret }}
{{- .Values.externalDatabase.existingSecret }}
{{- else }}
{{- printf "%s-external-db" (include "bizon-platform.fullname" .) }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Database URL (for asyncpg)
*/}}
{{- define "bizon-platform.databaseUrl" -}}
postgresql+asyncpg://$(DB_USERNAME):$(DB_PASSWORD)@{{ include "bizon-platform.postgresql.host" . }}:{{ include "bizon-platform.postgresql.port" . }}/{{ include "bizon-platform.postgresql.database" . }}
{{- end }}

{{/*
Encryption key secret name
*/}}
{{- define "bizon-platform.encryptionKeySecretName" -}}
{{- if .Values.security.existingEncryptionKeySecret }}
{{- .Values.security.existingEncryptionKeySecret }}
{{- else }}
{{- printf "%s-secrets" (include "bizon-platform.fullname" .) }}
{{- end }}
{{- end }}

{{/*
Admin password secret name
*/}}
{{- define "bizon-platform.adminPasswordSecretName" -}}
{{- if .Values.security.existingAdminPasswordSecret }}
{{- .Values.security.existingAdminPasswordSecret }}
{{- else }}
{{- printf "%s-secrets" (include "bizon-platform.fullname" .) }}
{{- end }}
{{- end }}

{{/*
Git token secret name
*/}}
{{- define "bizon-platform.gitTokenSecretName" -}}
{{- if .Values.gitSync.existingTokenSecret }}
{{- .Values.gitSync.existingTokenSecret }}
{{- else }}
{{- printf "%s-secrets" (include "bizon-platform.fullname" .) }}
{{- end }}
{{- end }}

{{/*
Git webhook secret name
*/}}
{{- define "bizon-platform.gitWebhookSecretName" -}}
{{- if .Values.gitSync.existingWebhookSecret }}
{{- .Values.gitSync.existingWebhookSecret }}
{{- else }}
{{- printf "%s-secrets" (include "bizon-platform.fullname" .) }}
{{- end }}
{{- end }}

{{/*
CORS allowed origins as JSON array string
*/}}
{{- define "bizon-platform.corsAllowedOrigins" -}}
{{- if kindIs "slice" .Values.config.corsAllowedOrigins }}
{{- .Values.config.corsAllowedOrigins | toJson }}
{{- else }}
{{- .Values.config.corsAllowedOrigins }}
{{- end }}
{{- end }}

{{/*
Image pull secrets
*/}}
{{- define "bizon-platform.imagePullSecrets" -}}
{{- with .Values.global.imagePullSecrets }}
imagePullSecrets:
{{- toYaml . | nindent 2 }}
{{- end }}
{{- end }}
