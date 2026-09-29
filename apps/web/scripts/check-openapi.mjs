import { readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import ts from 'typescript'

const clientPath = fileURLToPath(new URL('../src/lib/api.ts', import.meta.url))
const source = ts.createSourceFile(clientPath, await readFile(clientPath, 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)

function routeText(node) {
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) return node.text
  if (!ts.isTemplateExpression(node)) return null
  return node.templateSpans.reduce((path, span) => `${path}{}${span.literal.text}`, node.head.text)
}

function methodFromOptions(node) {
  if (!node || !ts.isObjectLiteralExpression(node)) return 'GET'
  const method = node.properties.find((property) => ts.isPropertyAssignment(property) && property.name.getText(source) === 'method')
  return method && ts.isPropertyAssignment(method) && ts.isStringLiteral(method.initializer)
    ? method.initializer.text.toUpperCase() : 'GET'
}

const used = new Set()
function visit(node) {
  if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) && ['request', 'fetch'].includes(node.expression.text)) {
    let route = node.arguments[0] && routeText(node.arguments[0])
    if (route) {
      if (node.expression.text === 'fetch') route = route.replace(/^\{\}/, '')
      if (route.startsWith('/')) used.add(`${methodFromOptions(node.arguments[1])} /api${route.replace(/\{[^}]*\}/g, '{}')}`)
    }
  }
  ts.forEachChild(node, visit)
}
visit(source)

if (used.size < 20) throw new Error(`Only ${used.size} client routes were found; check the extractor before trusting this result.`)

let schema
let sourceLabel
if (process.env.OPENAPI_FILE) {
  sourceLabel = process.env.OPENAPI_FILE
  schema = JSON.parse(await readFile(sourceLabel, 'utf8'))
} else {
  sourceLabel = process.env.OPENAPI_URL || 'http://127.0.0.1:8000/openapi.json'
  const response = await fetch(sourceLabel)
  if (!response.ok) throw new Error(`Could not load OpenAPI schema: HTTP ${response.status} from ${sourceLabel}`)
  schema = await response.json()
}

const available = new Set(Object.entries(schema.paths || {}).flatMap(([path, operations]) =>
  Object.keys(operations).filter((method) => ['get', 'post', 'put', 'patch', 'delete'].includes(method))
    .map((method) => `${method.toUpperCase()} ${path.replace(/\{[^}]+\}/g, '{}')}`),
))
const missing = [...used].filter((entry) => !available.has(entry)).sort()
if (missing.length) throw new Error(`Client methods missing from OpenAPI:\n${missing.map((entry) => `  ${entry}`).join('\n')}`)
const uploadSchema = schema.paths?.['/api/documents']?.post?.requestBody?.content?.['multipart/form-data']?.schema
const uploadDefinition = uploadSchema?.$ref
  ? schema.components?.schemas?.[uploadSchema.$ref.split('/').pop()]
  : uploadSchema
for (const field of ['file', 'category', 'authority']) {
  if (!uploadDefinition?.properties?.[field]) throw new Error(`Document upload field ${field} is missing from OpenAPI.`)
}
console.log(`OpenAPI contract: ${used.size} client route/method pairs verified against ${sourceLabel}.`)
