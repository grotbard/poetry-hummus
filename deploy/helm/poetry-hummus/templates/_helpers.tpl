{{- define "poetry-hummus.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "poetry-hummus.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name (include "poetry-hummus.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "poetry-hummus.labels" -}}
app.kubernetes.io/name: {{ include "poetry-hummus.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end -}}

{{- /* Name of the Secret holding credentials, managed or chart-created. */ -}}
{{- define "poetry-hummus.secretName" -}}
{{- if .Values.secrets.existingSecret -}}
{{- .Values.secrets.existingSecret -}}
{{- else -}}
{{- printf "%s-secrets" (include "poetry-hummus.fullname" .) -}}
{{- end -}}
{{- end -}}

{{- /*
Environment shared by the API deployment and the migration job.
Non-secret values come from values.yaml; secrets are referenced by key so
they are never rendered into the manifest.
*/ -}}
{{- define "poetry-hummus.apiEnv" -}}
{{- $db := .Values.config.database -}}
- name: POETRY_APP_ENV
  value: {{ .Values.config.appEnv | quote }}
- name: POETRY_FRONTEND_URL
  value: {{ .Values.config.frontendUrl | quote }}
- name: POETRY_PUBLIC_API_URL
  value: {{ .Values.config.publicApiUrl | quote }}
- name: POETRY_DB__POOL_SIZE
  value: {{ $db.poolSize | quote }}
- name: POETRY_DB__MAX_OVERFLOW
  value: {{ $db.maxOverflow | quote }}
- name: POETRY_DB__POOL_TIMEOUT_SECONDS
  value: {{ $db.poolTimeoutSeconds | quote }}
- name: POETRY_DB__POOL_RECYCLE_SECONDS
  value: {{ $db.poolRecycleSeconds | quote }}
- name: POETRY_DB__POOL_PRE_PING
  value: {{ $db.poolPrePing | quote }}
- name: POETRY_DB__ECHO_SQL
  value: {{ $db.echoSql | quote }}
- name: POETRY_LOYALTY__COINS_PER_SHEKEL
  value: {{ .Values.config.loyalty.coinsPerShekel | quote }}
- name: POETRY_LOYALTY__SIGNUP_BONUS_COINS
  value: {{ .Values.config.loyalty.signupBonusCoins | quote }}
{{- /* Assembled here so the password stays a secret reference. */}}
- name: DB_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ include "poetry-hummus.secretName" . }}
      key: {{ .Values.secrets.keys.databasePassword }}
- name: POETRY_DB__URL
  value: "postgresql+asyncpg://{{ $db.user }}:$(DB_PASSWORD)@{{ $db.host }}:{{ $db.port }}/{{ $db.name }}?ssl={{ $db.sslMode }}"
- name: POETRY_SECURITY__SECRET_KEY
  valueFrom:
    secretKeyRef:
      name: {{ include "poetry-hummus.secretName" . }}
      key: {{ .Values.secrets.keys.secretKey }}
- name: POETRY_GOOGLE__CLIENT_ID
  valueFrom:
    secretKeyRef:
      name: {{ include "poetry-hummus.secretName" . }}
      key: {{ .Values.secrets.keys.googleClientId }}
- name: POETRY_GOOGLE__CLIENT_SECRET
  valueFrom:
    secretKeyRef:
      name: {{ include "poetry-hummus.secretName" . }}
      key: {{ .Values.secrets.keys.googleClientSecret }}
- name: POETRY_ADMIN__EMAIL
  valueFrom:
    secretKeyRef:
      name: {{ include "poetry-hummus.secretName" . }}
      key: {{ .Values.secrets.keys.adminEmail }}
      optional: true
- name: POETRY_ADMIN__PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ include "poetry-hummus.secretName" . }}
      key: {{ .Values.secrets.keys.adminPassword }}
      optional: true
{{- end -}}
