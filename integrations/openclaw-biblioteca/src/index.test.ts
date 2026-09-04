import { afterEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { apiRequest } from "./index.js";

afterEach(() => vi.unstubAllGlobals());

describe("Biblioteca Kindle plugin", () => {
  it("declares stable, library-specific tool names", () => {
    const manifest = JSON.parse(readFileSync(new URL("../openclaw.plugin.json", import.meta.url), "utf8"));
    expect(manifest.contracts.tools).toEqual([
      "biblioteca_status", "biblioteca_buscar_libros", "biblioteca_obtener_libro",
      "biblioteca_listar_perfiles", "biblioteca_listar_conversaciones",
      "biblioteca_crear_conversacion", "biblioteca_obtener_conversacion",
      "biblioteca_obtener_contexto", "biblioteca_actualizar_contexto",
      "biblioteca_buscar_contexto", "biblioteca_preparar_turno",
      "biblioteca_completar_turno",
    ]);
  });

  it("calls only the configured API with its bearer token", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ ready: true }) });
    vi.stubGlobal("fetch", fetchMock);
    await apiRequest("/status", { baseUrl: "http://127.0.0.1:9000/", token: "private-token" });
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0][0]).toBe("http://127.0.0.1:9000/api/openclaw/v1/status");
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe("Bearer private-token");
  });

  it("fails closed when no token is configured", async () => {
    delete process.env.BIBLIOTECA_OPENCLAW_TOKEN;
    await expect(apiRequest("/status", {})).rejects.toThrow("Falta BIBLIOTECA_OPENCLAW_TOKEN");
  });
});
