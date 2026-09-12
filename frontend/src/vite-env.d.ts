/// <reference types="vite/client" />

/** Browser-visible configuration. Never add a secret to this list. */
interface ImportMetaEnv {
  readonly VITE_SUPABASE_URL?: string
  readonly VITE_SUPABASE_PUBLISHABLE_KEY?: string
  /** Overrides the default relative '/api' base. Rarely needed in development. */
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
