function hasText(value) {
  return Boolean(String(value || '').trim())
}

export function validateProfileSettings(payload) {
  if (!payload?.ai) {
    return '缺少 AI 配置。'
  }

  if (payload.ai.provider === 'ollama') {
    return hasText(payload.ai.ollama?.baseUrl) && hasText(payload.ai.ollama?.model)
      ? ''
      : '选择 Ollama 时需要填写 Base URL 和 Model。'
  }

  if (payload.ai.provider === 'openai-compatible') {
    const openaiConfig = payload.ai.openaiCompatible
    return hasText(openaiConfig?.apiKey) && hasText(openaiConfig?.baseUrl) && hasText(openaiConfig?.model)
      ? ''
      : '选择 OpenAI 兼容接口时需要填写 API Key、Base URL 和 Model。'
  }

  return '不支持的 AI provider。'
}
