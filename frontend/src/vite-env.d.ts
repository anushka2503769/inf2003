/// <reference types="vite/client" />

/** Browser-visible configuration. Never add a secret to this list. */
interface ImportMetaEnv {
  readonly VITE_SUPABASE_URL?: string
  readonly VITE_SUPABASE_PUBLISHABLE_KEY?: string
  /** Overrides the default relative '/api' base. Rarely needed in development. */
  readonly VITE_API_BASE_URL?: string
  /** 'mock' serves synthetic data on Discover, Vault and Skill Gap instead of the API. */
  readonly VITE_DATA?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
