type Config = {
    baseUrl?: string;
    token?: string;
};
export declare function apiRequest(path: string, config: Config, signal?: AbortSignal, options?: {
    method?: string;
    body?: unknown;
}): Promise<unknown>;
declare const _default: import("openclaw/plugin-sdk/tool-plugin").DefinedToolPluginEntry;
export default _default;
