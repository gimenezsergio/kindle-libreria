import { Type } from "typebox";
import { defineToolPlugin } from "openclaw/plugin-sdk/tool-plugin";

const configSchema = Type.Object({
  baseUrl: Type.Optional(Type.String({ description: "Private Biblioteca Kindle API base URL." })),
  token: Type.Optional(Type.String({ minLength: 1, description: "Bearer token dedicated to OpenClaw. Prefer the BIBLIOTECA_OPENCLAW_TOKEN environment variable." })),
}, { additionalProperties: false });

type Config = { baseUrl?: string; token?: string };

export async function apiRequest(path: string, config: Config, signal?: AbortSignal,
  options: { method?: string; body?: unknown } = {}): Promise<unknown> {
  const baseUrl = (config.baseUrl ?? "http://127.0.0.1:8000").replace(/\/$/, "");
  const token = config.token ?? process.env.BIBLIOTECA_OPENCLAW_TOKEN;
  if (!token) throw new Error("Falta BIBLIOTECA_OPENCLAW_TOKEN para consultar Biblioteca Kindle");
  const response = await fetch(`${baseUrl}/api/openclaw/v1${path}`, {
    method: options.method ?? "GET",
    headers: { Authorization: `Bearer ${token}`,
      ...(options.body === undefined ? {} : { "Content-Type": "application/json" }) },
    body: options.body === undefined ? undefined : JSON.stringify(options.body), signal,
  });
  const data = await response.json().catch(() => ({ error: `HTTP ${response.status}` }));
  if (!response.ok) {
    const message = typeof data === "object" && data && "error" in data
      ? String((data as { error: unknown }).error)
      : `Biblioteca Kindle respondió HTTP ${response.status}`;
    throw new Error(message);
  }
  return data;
}

const searchScope = Type.Union([
  Type.Literal("library"), Type.Literal("current"), Type.Literal("selected"),
]);

export default defineToolPlugin({
  id: "biblioteca-kindle",
  name: "Biblioteca Kindle",
  description: "Search a private Kindle library and hold persistent, evidence-backed reading conversations.",
  configSchema,
  tools: (tool) => [
    tool({
      name: "biblioteca_status", label: "Estado de Biblioteca Kindle",
      description: "Check whether the private Biblioteca Kindle API is available.",
      parameters: Type.Object({}),
      execute: (_params, config, context) => apiRequest("/status", config, context.signal),
    }),
    tool({
      name: "biblioteca_buscar_libros", label: "Buscar libros",
      description: "Find books by title or author before choosing a stable work_id. Ask the user when several results are plausible.",
      parameters: Type.Object({ query: Type.String(), limit: Type.Optional(Type.Integer({ minimum: 1, maximum: 20 })) }),
      execute: ({ query, limit }, config, context) => apiRequest(
        `/works?q=${encodeURIComponent(query)}&limit=${limit ?? 8}`, config, context.signal),
    }),
    tool({
      name: "biblioteca_obtener_libro", label: "Obtener libro",
      description: "Get the canonical title, author and annotation count for one stable work_id.",
      parameters: Type.Object({ work_id: Type.String() }),
      execute: ({ work_id }, config, context) => apiRequest(`/works/${encodeURIComponent(work_id)}`, config, context.signal),
    }),
    tool({
      name: "biblioteca_listar_perfiles", label: "Listar perfiles de lectura",
      description: "List active reading-companion profiles. Prefer the default unless the user chooses another.",
      parameters: Type.Object({}),
      execute: (_params, config, context) => apiRequest("/profiles", config, context.signal),
    }),
    tool({
      name: "biblioteca_listar_conversaciones", label: "Listar conversaciones",
      description: "List persistent conversations for a selected book.",
      parameters: Type.Object({ work_id: Type.String() }),
      execute: ({ work_id }, config, context) => apiRequest(`/works/${encodeURIComponent(work_id)}/conversations`, config, context.signal),
    }),
    tool({
      name: "biblioteca_crear_conversacion", label: "Crear conversación",
      description: "Create a persistent conversation after the book and profile have been selected.",
      parameters: Type.Object({ work_id: Type.String(), profile_id: Type.String(), title: Type.Optional(Type.String()) }),
      execute: ({ work_id, profile_id, title }, config, context) => apiRequest(
        `/works/${encodeURIComponent(work_id)}/conversations`, config, context.signal,
        { method: "POST", body: { profile_id, title: title ?? "" } }),
    }),
    tool({
      name: "biblioteca_obtener_conversacion", label: "Obtener conversación",
      description: "Read a persistent conversation and the human-readable sources used in its answers.",
      parameters: Type.Object({ conversation_id: Type.String() }),
      execute: ({ conversation_id }, config, context) => apiRequest(`/conversations/${encodeURIComponent(conversation_id)}`, config, context.signal),
    }),
    tool({
      name: "biblioteca_obtener_contexto", label: "Obtener material de lectura",
      description: "List selectable personal notes and Kindle annotations for the conversation's book.",
      parameters: Type.Object({ conversation_id: Type.String() }),
      execute: ({ conversation_id }, config, context) => apiRequest(`/conversations/${encodeURIComponent(conversation_id)}/context`, config, context.signal),
    }),
    tool({
      name: "biblioteca_actualizar_contexto", label: "Seleccionar material de lectura",
      description: "Replace temporary selected notes and annotations. Pinned sources are preserved.",
      parameters: Type.Object({ conversation_id: Type.String(), personal_note_ids: Type.Array(Type.String()), annotation_ids: Type.Array(Type.String()) }),
      execute: ({ conversation_id, personal_note_ids, annotation_ids }, config, context) => apiRequest(
        `/conversations/${encodeURIComponent(conversation_id)}/context`, config, context.signal,
        { method: "PUT", body: { personal_note_ids, annotation_ids } }),
    }),
    tool({
      name: "biblioteca_buscar_contexto", label: "Buscar evidencia en la biblioteca",
      description: "Preview up to eight traceable sources relevant to a question. This does not send full book texts.",
      parameters: Type.Object({ conversation_id: Type.String(), query: Type.String(), search_scope: Type.Optional(searchScope), search_work_ids: Type.Optional(Type.Array(Type.String())) }),
      execute: ({ conversation_id, query, search_scope, search_work_ids }, config, context) => apiRequest(
        `/conversations/${encodeURIComponent(conversation_id)}/library-search`, config, context.signal,
        { method: "POST", body: { search_query: query, search_scope: search_scope ?? "library", search_work_ids: search_work_ids ?? [] } }),
    }),
    tool({
      name: "biblioteca_preparar_turno", label: "Preparar turno de lectura",
      description: "Persist the user message and return profile instructions, history, selected material and retrieved evidence needed to answer.",
      parameters: Type.Object({
        conversation_id: Type.String(), content: Type.String(),
        search_library: Type.Optional(Type.Boolean()), search_scope: Type.Optional(searchScope),
        search_work_ids: Type.Optional(Type.Array(Type.String())), library_source_keys: Type.Optional(Type.Array(Type.String())),
        personal_note_ids: Type.Optional(Type.Array(Type.String())), annotation_ids: Type.Optional(Type.Array(Type.String())),
      }),
      execute: ({ conversation_id, ...body }, config, context) => apiRequest(
        `/conversations/${encodeURIComponent(conversation_id)}/turns`, config, context.signal,
        { method: "POST", body: { search_scope: "library", search_library: true, ...body } }),
    }),
    tool({
      name: "biblioteca_completar_turno", label: "Guardar respuesta de lectura",
      description: "Persist the final answer and its prepared sources. Retrying the same turn_id is idempotent.",
      parameters: Type.Object({ turn_id: Type.String(), content: Type.String() }),
      execute: ({ turn_id, content }, config, context) => apiRequest(
        `/turns/${encodeURIComponent(turn_id)}/complete`, config, context.signal,
        { method: "POST", body: { content } }),
    }),
  ],
});
