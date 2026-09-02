{{- define "arbiter.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "arbiter.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "arbiter.labels" -}}
app.kubernetes.io/name: {{ include "arbiter.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end -}}

{{- define "arbiter.selectorLabels" -}}
app.kubernetes.io/name: {{ include "arbiter.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "arbiter.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "arbiter.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{- define "arbiter.secretName" -}}
{{- if .Values.secret.existingSecret -}}
{{- .Values.secret.existingSecret -}}
{{- else -}}
{{- printf "%s-secret" (include "arbiter.fullname" .) -}}
{{- end -}}
{{- end -}}

{{- define "arbiter.apiImage" -}}
{{- printf "%s/%s-api:%s" .Values.image.registry .Values.image.repository .Values.image.apiTag -}}
{{- end -}}

{{- define "arbiter.webImage" -}}
{{- printf "%s/%s-web:%s" .Values.image.registry .Values.image.repository .Values.image.webTag -}}
{{- end -}}

{{/* Shared env: config from the ConfigMap, secrets from the Secret. */}}
{{- define "arbiter.envFrom" -}}
- configMapRef:
    name: {{ include "arbiter.fullname" . }}-config
- secretRef:
    name: {{ include "arbiter.secretName" . }}
{{- end -}}
