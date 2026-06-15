import Vue from 'vue'
import { normalizeError, sendChatStream } from '../api/api'

const TOOL_RESULT_PLACEHOLDER = '等待结果...'

export function createChatSession() {
  return {
    messages: [],
    streamingContent: '',
    loading: false,
    sending: false,
    error: '',
  }
}

export function activeChatSession(state) {
  const profileId = state.selectedProfileId
  return profileId ? state.chatSessions[profileId] || createChatSession() : createChatSession()
}

export function ensureChatSession(state, profileId) {
  if (!state.chatSessions[profileId]) {
    Vue.set(state.chatSessions, profileId, createChatSession())
  }
  return state.chatSessions[profileId]
}

export function deleteChatSession(state, profileId) {
  Vue.delete(state.chatSessions, profileId)
}

function now() {
  return new Date().toISOString()
}

function shortToolResult(result) {
  return result.length > 500 ? `${result.slice(0, 500)}...` : result
}

function removeMessage(messages, target) {
  const index = messages.indexOf(target)
  if (index !== -1) {
    messages.splice(index, 1)
  }
}

function finishSending(session) {
  session.streamingContent = ''
  session.sending = false
}

function failMessage(session, assistant, error) {
  removeMessage(session.messages, assistant)
  finishSending(session)
  session.error = error
}

function appendPendingMessage(session, question) {
  session.messages.push({ role: 'user', content: question, timestamp: now() })

  const assistant = { role: 'assistant', content: '', timestamp: '' }
  session.messages.push(assistant)
  return assistant
}

function appendToolPlaceholders(session, assistant, pendingTools, tool) {
  const assistantIndex = session.messages.indexOf(assistant)
  if (assistantIndex === -1) return

  session.messages.splice(assistantIndex, 0, {
    role: 'tool_call',
    content: `正在调用: ${tool}`,
    timestamp: now(),
  })

  const resultIndex = assistantIndex + 1
  session.messages.splice(resultIndex, 0, {
    role: 'tool_result',
    content: TOOL_RESULT_PLACEHOLDER,
    timestamp: now(),
  })
  pendingTools.push({ tool, index: resultIndex, message: session.messages[resultIndex] })
}

function updateToolResult(session, pendingTools, tool, result) {
  const entry = pendingTools.find((item) => item.tool === tool && item.message)
  if (entry?.message) {
    entry.message.content = shortToolResult(result)
    return
  }

  const indexedEntry = pendingTools.find(
    (item) => item.tool === tool &&
      session.messages[item.index]?.content === TOOL_RESULT_PLACEHOLDER
  )
  if (indexedEntry && session.messages[indexedEntry.index]) {
    session.messages[indexedEntry.index].content = shortToolResult(result)
  }
}

export async function sendProfileMessage(state, profileId, question, { onDone } = {}) {
  if (!profileId) return

  const session = ensureChatSession(state, profileId)
  if (session.sending) return

  session.sending = true
  session.error = ''
  session.streamingContent = ''

  const assistant = appendPendingMessage(session, question)
  const pendingTools = []

  try {
    await sendChatStream(profileId, question, 3, {
      onToken: (content) => {
        session.streamingContent += content
        assistant.content += content
      },
      onDone: (content) => {
        if (typeof content === 'string') assistant.content = content
        assistant.timestamp = now()
        finishSending(session)
        onDone?.()
      },
      onError: (error) => failMessage(session, assistant, error),
      onToolStart: (tool) => appendToolPlaceholders(session, assistant, pendingTools, tool),
      onToolResult: (tool, result) => updateToolResult(session, pendingTools, tool, result),
    })
  } catch (error) {
    failMessage(session, assistant, normalizeError(error))
  }
}
