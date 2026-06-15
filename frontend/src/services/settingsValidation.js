export function validateProfileSettings(payload) {
  if (!payload?.ai) {
    return '缺少 AI 配置。'
  }

  if (payload.ai.provider === 'ollama') {
    return payload.ai.ollama?.baseUrl && payload.ai.ollama?.model
      ? ''
      : '选择 Ollama 时需要填写 Base URL 和 Model。'
  }

  const openaiConfig = payload.ai.openaiCompatible
  return openaiConfig?.apiKey && openaiConfig?.baseUrl && openaiConfig?.model
    ? ''
    : '选择 OpenAI 兼容接口时需要填写 API Key、Base URL 和 Model。'
}
