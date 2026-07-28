import { appendFileSync, mkdirSync, renameSync, writeFileSync } from 'node:fs'
import { createServer } from 'node:http'
import { dirname, resolve } from 'node:path'

const MAX_REQUEST_BYTES = 1024 * 1024

function requiredEnvironmentValue(name) {
  const value = process.env[name]?.trim()
  if (!value) {
    throw new Error(`${name} is required.`)
  }
  return value
}

function requiredArgument(name) {
  const index = process.argv.indexOf(name)
  const value = index >= 0 ? process.argv[index + 1]?.trim() : ''
  if (!value) {
    throw new Error(`${name} is required.`)
  }
  return resolve(value)
}

const apiKey = requiredEnvironmentValue('NOVWR_DESKTOP_PROVIDER_API_KEY')
const model = requiredEnvironmentValue('NOVWR_DESKTOP_PROVIDER_MODEL')
const readyFile = requiredArgument('--ready-file')
const logFile = requiredArgument('--log-file')
const requestCounts = {
  basic: 0,
  stream: 0,
  json_mode: 0,
}

mkdirSync(dirname(logFile), { recursive: true })

function log(event, details = {}) {
  appendFileSync(logFile, `${JSON.stringify({ event, ...details })}\n`, 'utf8')
}

function sendJson(response, statusCode, payload) {
  const body = JSON.stringify(payload)
  response.writeHead(statusCode, {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': Buffer.byteLength(body),
  })
  response.end(body)
}

async function readJsonBody(request) {
  const chunks = []
  let byteLength = 0
  for await (const chunk of request) {
    byteLength += chunk.length
    if (byteLength > MAX_REQUEST_BYTES) {
      throw new Error('request_too_large')
    }
    chunks.push(chunk)
  }
  return JSON.parse(Buffer.concat(chunks).toString('utf8'))
}

function completionEnvelope(content, requestId, created) {
  return {
    id: requestId,
    object: 'chat.completion',
    created,
    model,
    choices: [{
      index: 0,
      message: { role: 'assistant', content },
      finish_reason: 'stop',
    }],
    usage: {
      prompt_tokens: 1,
      completion_tokens: 1,
      total_tokens: 2,
    },
  }
}

function sendStream(response, requestId, created, includeUsage) {
  response.writeHead(200, {
    'Content-Type': 'text/event-stream; charset=utf-8',
    'Cache-Control': 'no-cache',
    Connection: 'keep-alive',
  })
  const chunks = [
    {
      id: requestId,
      object: 'chat.completion.chunk',
      created,
      model,
      choices: [{
        index: 0,
        delta: { role: 'assistant', content: 'ok' },
        finish_reason: null,
      }],
    },
    {
      id: requestId,
      object: 'chat.completion.chunk',
      created,
      model,
      choices: [{ index: 0, delta: {}, finish_reason: 'stop' }],
    },
  ]
  if (includeUsage) {
    chunks.push({
      id: requestId,
      object: 'chat.completion.chunk',
      created,
      model,
      choices: [],
      usage: {
        prompt_tokens: 1,
        completion_tokens: 1,
        total_tokens: 2,
      },
    })
  }
  for (const chunk of chunks) {
    response.write(`data: ${JSON.stringify(chunk)}\n\n`)
  }
  response.end('data: [DONE]\n\n')
}

const server = createServer(async (request, response) => {
  if (request.method === 'GET' && request.url === '/health') {
    sendJson(response, 200, { status: 'healthy', requests: requestCounts })
    return
  }
  if (request.method !== 'POST' || request.url !== '/v1/chat/completions') {
    sendJson(response, 404, { error: { message: 'Not found', type: 'invalid_request_error' } })
    return
  }
  if (request.headers.authorization !== `Bearer ${apiKey}`) {
    sendJson(response, 401, { error: { message: 'Invalid API key', type: 'authentication_error' } })
    return
  }

  let body
  try {
    body = await readJsonBody(request)
  } catch (error) {
    const message = error instanceof Error && error.message === 'request_too_large'
      ? 'Request body is too large'
      : 'Request body must be valid JSON'
    sendJson(response, 400, { error: { message, type: 'invalid_request_error' } })
    return
  }
  if (body === null || typeof body !== 'object' || Array.isArray(body)) {
    sendJson(response, 400, { error: { message: 'Request body must be an object', type: 'invalid_request_error' } })
    return
  }
  if (body.model !== model) {
    sendJson(response, 400, { error: { message: 'Unexpected model', type: 'invalid_request_error' } })
    return
  }

  const requestId = `chatcmpl-novwr-${Date.now()}`
  const created = Math.floor(Date.now() / 1000)
  if (body.stream === true) {
    requestCounts.stream += 1
    log('request', { mode: 'stream' })
    sendStream(response, requestId, created, body.stream_options?.include_usage === true)
    return
  }
  if (body.response_format?.type === 'json_object') {
    requestCounts.json_mode += 1
    log('request', { mode: 'json_mode' })
    sendJson(response, 200, completionEnvelope('{"ok":true}', requestId, created))
    return
  }
  if (body.response_format !== undefined) {
    sendJson(response, 400, { error: { message: 'Unsupported response format', type: 'invalid_request_error' } })
    return
  }

  requestCounts.basic += 1
  log('request', { mode: 'basic' })
  sendJson(response, 200, completionEnvelope('ok', requestId, created))
})

server.on('clientError', (error, socket) => {
  log('client_error', { message: error.message })
  socket.end('HTTP/1.1 400 Bad Request\r\n\r\n')
})

server.listen(0, '127.0.0.1', () => {
  const address = server.address()
  if (address === null || typeof address === 'string') {
    throw new Error('Provider stub did not bind a TCP port.')
  }
  const origin = `http://127.0.0.1:${address.port}`
  mkdirSync(dirname(readyFile), { recursive: true })
  const temporaryReadyFile = `${readyFile}.${process.pid}.tmp`
  writeFileSync(temporaryReadyFile, `${JSON.stringify({ origin, base_url: `${origin}/v1` })}\n`, 'utf8')
  renameSync(temporaryReadyFile, readyFile)
  log('ready', { origin })
})

server.on('error', (error) => {
  log('server_error', { message: error.message })
  process.exitCode = 1
})
